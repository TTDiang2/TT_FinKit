"""Money-market fund (货币基金) support.

MMFs have no unit NAV (pinned at 1.0); Eastmoney pingzhongdata flags them
with `ishb=true` and carries two yield series instead:
- Data_millionCopiesIncome  = [[ts, per-10k daily income], ...]  (万份收益)
- Data_sevenDaysYearIncome  = [[ts, annualized %], ...]          (七日年化)

Model (user-approved): per-10k income reinvested into shares daily
(万份收益再投，份额每日增加). The combination NAV keeps nav=1.0 for MMFs
and grows the share count instead, so buy/redeem days stay jump-free.
"""
from __future__ import annotations

import re
import time as _time
from datetime import datetime, timezone

import httpx

_CST = timezone.utc  # only used for timestamp → date; UTC == CST date boundary for funds
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fund.eastmoney.com/",
}

_MMF_TEXT_CACHE: dict[str, tuple[float, str]] = {}
_MMF_TEXT_TTL = 600.0


class MoneyMarketFundError(RuntimeError):
    pass


async def _fetch_payload(symbol: str) -> str:
    cached = _MMF_TEXT_CACHE.get(symbol)
    if cached and _time.monotonic() - cached[0] < _MMF_TEXT_TTL:
        return cached[1]
    url = f"https://fund.eastmoney.com/pingzhongdata/{symbol}.js"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_HEADERS, timeout=20.0)
        r.raise_for_status()
        text = r.text
    _MMF_TEXT_CACHE[symbol] = (_time.monotonic(), text)
    return text


def _slice_pairs(text: str, marker: str) -> list[tuple[int, float]]:
    """[[ts, val], ...] arrays via slicing + small regex (payload is ~700KB)."""
    idx = text.find(marker)
    if idx == -1:
        return []
    seg = text[idx:text.find("];", idx)]
    return [(int(ts), float(v)) for ts, v in re.findall(r"\[([0-9]+),([0-9.]+)\]", seg)]


def money_market_nav_series(text: str, begin: str, end: str) -> list[dict]:
    """Par-priced daily points (close=1.0) over the income dates in [begin, end]."""
    out = []
    for ts, _v in _slice_pairs(text, "Data_millionCopiesIncome"):
        d = datetime.fromtimestamp(ts / 1000, tz=_CST).strftime("%Y-%m-%d")
        if begin <= d <= end:
            out.append({"date": d, "close": 1.0})
    return out


async def probe(symbol: str) -> tuple[bool, float | None]:
    """Non-raising detection: (is_money_market, latest_seven_day)."""
    try:
        text = await _fetch_payload(symbol)
        m = re.search(r'ishb\s*=\s*"?([^";]*)', text)
        if not (m and m.group(1) == "true"):
            return False, None
        pairs = _slice_pairs(text, "Data_sevenDaysYearIncome")
        return True, (pairs[-1][1] if pairs else None)
    except (httpx.HTTPError, MoneyMarketFundError, ValueError):
        return False, None


async def is_money_market(symbol: str) -> bool:
    text = await _fetch_payload(symbol)
    m = re.search(r'ishb\s*=\s*"?([^";]*)', text)
    return bool(m and m.group(1) == "true")


async def fetch_mmf_yields(symbol: str, begin: str, end: str) -> list[dict]:
    """Daily yields in [begin, end]: [{date, income_per_10k, seven_day}]."""
    text = await _fetch_payload(symbol)
    m = re.search(r'ishb\s*=\s*"?([^";]*)', text)
    if not (m and m.group(1) == "true"):
        raise MoneyMarketFundError(f"{symbol} is not a money-market fund")
    income = {ts: v for ts, v in _slice_pairs(text, "Data_millionCopiesIncome")}
    seven = {ts: v for ts, v in _slice_pairs(text, "Data_sevenDaysYearIncome")}
    out = []
    for ts in sorted(income):
        d = datetime.fromtimestamp(ts / 1000, tz=_CST).strftime("%Y-%m-%d")
        if begin <= d <= end:
            out.append({
                "date": d,
                "income_per_10k": income[ts],
                "seven_day": seven.get(ts),
            })
    if not out:
        raise MoneyMarketFundError(f"no yield data for {symbol} in {begin}..{end}")
    return out


async def latest_seven_day(symbol: str) -> float | None:
    text = await _fetch_payload(symbol)
    pairs = _slice_pairs(text, "Data_sevenDaysYearIncome")
    if not pairs:
        return None
    return pairs[-1][1]


async def mmf_current_shares(symbol: str, evs: list) -> float:
    """Latest reinvested share count; market value is shares x 1.0.

    Falls back to the raw net share count when yields are unreachable, so
    the portfolio stays consistent offline.
    """
    if not evs:
        return 0.0
    begin = evs[0].event_date[:10]
    end = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        yields = await fetch_mmf_yields(symbol, begin, end)
    except MoneyMarketFundError:
        return sum(t.quantity or 0 for t in evs if t.event_type in ("buy", "sell"))
    dates = [y["date"] for y in yields]
    shares = await mmf_shares_by_date(symbol, dates, evs)
    return shares[dates[-1]] if shares else 0.0


async def mmf_shares_by_date(symbol: str, dates: list[str], evs: list) -> dict[str, float]:
    """Reinvested share count per date (units: MMF shares).

    New shares earn income from the next day (T+1 settlement); income accrues
    before same-day buys/sells are applied.
    """
    if not evs:
        return {}
    begin, end = dates[0], dates[-1]
    yields_by_date: dict[str, float] = {}
    try:
        for row in await fetch_mmf_yields(symbol, begin, end):
            yields_by_date[row["date"]] = row["income_per_10k"] / 10000.0
    except MoneyMarketFundError:
        return {}

    evs = sorted(evs, key=lambda t: t.event_date)
    shares = 0.0
    ei = 0
    out: dict[str, float] = {}
    for d in dates:
        y = yields_by_date.get(d)
        if y and shares > 0:
            shares *= 1.0 + y
        while ei < len(evs) and evs[ei].event_date[:10] <= d:
            shares += evs[ei].quantity or 0
            ei += 1
        if shares > 0:
            out[d] = shares
    return out
