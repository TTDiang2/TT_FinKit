"""Historical NAV/price series with a multi-source fallback chain.

Chain (first success wins):
  1. iFinD            — authoritative, needs credentials + iFinDPy
  2. Eastmoney (HTTP) — funds: pingzhongdata unit-NAV trend;
                        SH/SZ/HK: push2his daily kline (前复权)
  3. akshare          — lazy import; only required when Eastmoney changes/blocks

All sources return the same shape: [{"date": "YYYY-MM-DD", "close": float}, ...]
sorted ascending, filtered to [begin, end].
"""
from __future__ import annotations

import asyncio
import hashlib as _hashlib
import json as _json
import os as _os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from . import ifind_client

# Eastmoney JS timestamps are Beijing-time midnight (= UTC previous-day 16:00).
# Converting them in UTC shifts every date one day early — verified against
# akshare's F10 table: UTC conversion mismatches 90/92 days, CST matches 116/116.
_CST = timezone(timedelta(hours=8))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_EASTMONEY_SECID_PREFIX = {"SH": "1", "SZ": "0", "HK": "116"}


class NavHistoryError(RuntimeError):
    pass


import time as _time

_CACHE_TTL = 600.0
_nav_cache: dict[tuple, tuple[float, list[dict], str]] = {}

# Fund NAVs change once per trading day; a 12h disk cache survives backend
# restarts so cold starts skip the 30-90s multi-source refetch entirely.
_DISK_CACHE_TTL = 12 * 3600.0
_DISK_CACHE_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "cache", "nav_history")


def _disk_cache_path(key: tuple) -> str:
    return _os.path.join(_DISK_CACHE_DIR, _hashlib.md5(repr(key).encode()).hexdigest() + ".json")


def _load_disk_cache(key: tuple) -> Optional[tuple[list[dict], str]]:
    try:
        with open(_disk_cache_path(key), "r", encoding="utf-8") as f:
            data = _json.load(f)
        if _time.time() - float(data["ts"]) < _DISK_CACHE_TTL:
            return data["series"], data["source"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def _save_disk_cache(key: tuple, series: list[dict], source: str) -> None:
    try:
        _os.makedirs(_DISK_CACHE_DIR, exist_ok=True)
        path = _disk_cache_path(key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump({"ts": _time.time(), "source": source, "series": series}, f, ensure_ascii=False)
        _os.replace(tmp, path)
    except OSError:
        pass


async def fetch_history_series(
    symbol: str,
    exchange: str,
    begin: str,
    end: str,
    ifind_user: Optional[str] = None,
    ifind_pass: Optional[str] = None,
    force_money_market: bool = False,
) -> tuple[list[dict], str]:
    """Returns (series, source). Raises NavHistoryError when every source fails.

    force_money_market skips iFinD: money-market funds return no unit NAV, but
    iFinD sometimes answers with garbage (a non-empty mis-mapped series), which
    must not override the eastmoney income-based branch.
    """
    key = (symbol, (exchange or "").upper(), begin, end, force_money_market)
    cached = _nav_cache.get(key)
    if cached and _time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1], cached[2]

    disk = _load_disk_cache(key)
    if disk is not None:
        _nav_cache[key] = (_time.monotonic(), disk[0], disk[1])
        return disk[0], disk[1]

    series, source = await _fetch_uncached(
        symbol, exchange, begin, end, ifind_user, ifind_pass, force_money_market
    )
    _nav_cache[key] = (_time.monotonic(), series, source)
    _save_disk_cache(key, series, source)
    return series, source


_BENCHMARK_SYMBOL = "000300"
_BENCHMARK_EXCHANGE = "SH"


async def fetch_benchmark_series(begin: str, end: str) -> tuple[list[dict], str]:
    """沪深300 daily close series (Tencent ifzq → eastmoney kline → akshare fallback).

    Note: push2his.eastmoney.com RSTs Python TLS fingerprints (JA3), so the
    eastmoney kline path below is mostly a paper fallback; Tencent is primary.
    """
    key = ("benchmark", begin, end)
    cached = _nav_cache.get(key)
    if cached and _time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1], cached[2]

    disk = _load_disk_cache(key)
    if disk is not None:
        _nav_cache[key] = (_time.monotonic(), disk[0], disk[1])
        return disk[0], disk[1]

    errors: list[str] = []
    try:
        series = await _tencent_index_kline(begin, end)
        if series:
            _nav_cache[key] = (_time.monotonic(), series, "tencent")
            _save_disk_cache(key, series, "tencent")
            return series, "tencent"
        errors.append("tencent: empty series")
    except Exception as e:
        errors.append(f"tencent: {e}")

    try:
        series = await _eastmoney_kline(_BENCHMARK_SYMBOL, _BENCHMARK_EXCHANGE, begin, end)
        if series:
            _nav_cache[key] = (_time.monotonic(), series, "eastmoney")
            _save_disk_cache(key, series, "eastmoney")
            return series, "eastmoney"
        errors.append("eastmoney: empty series")
    except Exception as e:
        errors.append(f"eastmoney: {e}")

    try:
        series = await _akshare_index(begin, end)
        if series:
            _nav_cache[key] = (_time.monotonic(), series, "akshare")
            _save_disk_cache(key, series, "akshare")
            return series, "akshare"
        errors.append("akshare: not installed")
    except ImportError:
        errors.append("akshare: not installed")
    except Exception as e:
        errors.append(f"akshare: {e}")

    raise NavHistoryError("；".join(errors) or "无可用数据源")


async def _tencent_index_kline(begin: str, end: str) -> list[dict]:
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param=sh000300,day,{begin},{end},640,qfq"
    )
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_HEADERS, timeout=15.0)
        r.raise_for_status()
        data = r.json()
    node = (data.get("data") or {}).get("sh000300") or {}
    lines = node.get("day") or node.get("qfqday") or []
    out = []
    for parts in lines:
        # [date, open, close, high, low, volume]
        d = str(parts[0])[:10]
        if len(parts) >= 3 and _in_range(d, begin, end):
            out.append({"date": d, "close": float(parts[2])})
    return out


async def _akshare_index(begin: str, end: str) -> list[dict]:
    def _run():
        import akshare as ak

        return ak.index_zh_a_hist(
            symbol="000300",
            period="daily",
            start_date=begin.replace("-", ""),
            end_date=end.replace("-", ""),
        )

    df = await asyncio.to_thread(_run)
    out = []
    for _, row in df.iterrows():
        d = str(row["日期"])[:10]
        if _in_range(d, begin, end):
            out.append({"date": d, "close": float(row["收盘"])})
    return out


async def _fetch_uncached(
    symbol: str,
    exchange: str,
    begin: str,
    end: str,
    ifind_user: Optional[str] = None,
    ifind_pass: Optional[str] = None,
    force_money_market: bool = False,
) -> tuple[list[dict], str]:
    ex = (exchange or "").upper()
    errors: list[str] = []

    if ifind_user and ifind_pass and not force_money_market:
        try:
            series = await ifind_client.fetch_history_close(ifind_user, ifind_pass, symbol, ex, begin, end)
            if series:
                return series, "ifind"
            errors.append("ifind: empty series")
        except Exception as e:
            errors.append(f"ifind: {e}")

    try:
        series, src = await _eastmoney_history(symbol, ex, begin, end)
        if series:
            return series, src
        errors.append("eastmoney: empty series")
    except Exception as e:
        errors.append(f"eastmoney: {e}")

    try:
        series = await _akshare_history(symbol, ex, begin, end)
        if series:
            return series, "akshare"
        errors.append("akshare: empty series")
    except ImportError:
        errors.append("akshare: not installed")
    except Exception as e:
        errors.append(f"akshare: {e}")

    raise NavHistoryError("；".join(errors) or "无可用数据源")


def _in_range(d: str, begin: str, end: str) -> bool:
    return begin <= d <= end


async def _eastmoney_history(symbol: str, exchange: str, begin: str, end: str) -> tuple[list[dict], str]:
    if exchange == "FUND_CN":
        return await _eastmoney_fund_nav(symbol, begin, end)
    if exchange in _EASTMONEY_SECID_PREFIX:
        series = await _eastmoney_kline(symbol, exchange, begin, end)
        return series, "eastmoney"
    raise NavHistoryError(f"eastmoney: unsupported exchange {exchange!r}")


async def _eastmoney_fund_nav(symbol: str, begin: str, end: str) -> tuple[list[dict], str]:
    """pingzhongdata carries the full unit-NAV trend since inception (~700KB JS).

    String slicing instead of a DOTALL regex on the payload — regex over the
    whole blob causes catastrophic backtracking.
    """
    url = f"https://fund.eastmoney.com/pingzhongdata/{symbol}.js"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_HEADERS, timeout=20.0)
        r.raise_for_status()
        text = r.text
    idx = text.find("Data_netWorthTrend")
    if idx == -1:
        # money-market funds carry no unit NAV (pinned at 1.0); the income
        # dates still union into the combination curve so their trading days
        # participate in the NAV walk
        from . import money_market_fund as mmf

        if await mmf.is_money_market(symbol):
            return mmf.money_market_nav_series(text, begin, end), "eastmoney-money-market"
        raise NavHistoryError(f"eastmoney: no Data_netWorthTrend for {symbol}")
    seg = text[idx:text.find("];", idx)]
    pairs = re.findall(r'"x":([0-9]+),"y":([0-9.]+)', seg)
    out = []
    for ts, y in pairs:
        d = datetime.fromtimestamp(int(ts) / 1000, tz=_CST).strftime("%Y-%m-%d")
        if _in_range(d, begin, end):
            out.append({"date": d, "close": float(y)})
    return out, "eastmoney"


async def _eastmoney_kline(symbol: str, exchange: str, begin: str, end: str) -> list[dict]:
    secid = f"{_EASTMONEY_SECID_PREFIX[exchange]}.{symbol}"
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f53&klt=101&fqt=1"
        f"&beg={begin.replace('-', '')}&end={end.replace('-', '')}"
    )
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_HEADERS, timeout=15.0)
        r.raise_for_status()
        data = r.json()
    lines = (data.get("data") or {}).get("klines") or []
    out = []
    for line in lines:
        parts = line.split(",")
        if len(parts) >= 2 and _in_range(parts[0], begin, end):
            out.append({"date": parts[0], "close": float(parts[1])})
    return out


async def _akshare_history(symbol: str, exchange: str, begin: str, end: str) -> list[dict]:
    def _run():
        import akshare as ak
        if exchange == "FUND_CN":
            df = ak.fund_open_fund_info_em(symbol=symbol, period="D")
            date_col, close_col = "净值日期", "单位净值"
        elif exchange in ("SH", "SZ"):
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                    start_date=begin.replace("-", ""),
                                    end_date=end.replace("-", ""), adjust="qfq")
            date_col, close_col = "日期", "收盘"
        elif exchange == "HK":
            df = ak.stock_hk_hist(symbol=symbol, period="daily",
                                  start_date=begin.replace("-", ""),
                                  end_date=end.replace("-", ""), adjust="qfq")
            date_col, close_col = "日期", "收盘"
        else:
            raise NavHistoryError(f"akshare: unsupported exchange {exchange!r}")
        return df, date_col, close_col

    df, date_col, close_col = await asyncio.to_thread(_run)
    out = []
    for _, row in df.iterrows():
        d = str(row[date_col])[:10]
        if _in_range(d, begin, end):
            out.append({"date": d, "close": float(row[close_col])})
    return out
