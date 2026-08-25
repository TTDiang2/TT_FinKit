"""akshare data-source wrappers for the P1.2 factor sync engine.

Contract
--------
Every ``fetch_*`` function below returns ``list[tuple[date_str, value_float]]``
(date ``'YYYY-MM-DD'``, value float).  Empty list means *no data*; hard
failures (network, bad params, unexpected shape) raise.

Concurrency
-----------
akshare is a SYNC library.  These wrappers are plain sync functions; the async
layer (``asyncio.to_thread`` + ``asyncio.Semaphore(3)``) lives in
``factor_sync.py``.

Network notes (observed on akshare 1.18.88, verified live)
----------------------------------------------------------
* East Money ``push2his.eastmoney.com`` rejects the bare ``python-requests``
  User-Agent with ``ConnectionError``; a browser UA is required.
  ``_ensure_browser_ua()`` patches ``requests.utils.default_user_agent`` once.
* ``ak.index_zh_a_hist`` internally calls ``ak.index_code_id_map_em()`` which
  hits ``80.push2.eastmoney.com`` — frequently blocked by firewall/CDN.
  ``fetch_index_pct`` therefore falls back to a direct East Money kline call
  (same endpoint, browser UA, akshare's exact column mapping) when the stock
  wrapper raises ``ConnectionError``.
* ``ak.stock_hsgt_fund_flow_summary_em`` returns only the CURRENT trading-day
  snapshot (verified live: a single 交易日) -> ``fetch_northbound`` raises
  ``NoDataError``.
* ``ak.stock_individual_fund_flow_rank`` is a daily cross-section snapshot;
  history accumulation is handled by ``factor_sync`` via a JSON sidecar.

Registry mismatches observed (registry is the contract — adapt here, never
edit ``factor_registry.py``):
* ``macro_china_cpi_monthly`` 商品 column carries ``"中国CPI月率报告"`` while the
  registry ``inflation`` config uses item ``"CPI当月同比"`` — matched with a
  tolerant fallback (exact -> substring -> single-series).
* ``macro_china_pmi_yearly`` 商品 = ``"中国官方制造业PMI"`` vs registry item
  ``"官方制造业PMI"`` — handled by the same substring fallback.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

_AK = None


class NoDataError(Exception):
    """Data is not available (snapshot-only source, symbol not found, ...)."""


def _ak():
    """Lazily import akshare (keeps pytest fast — no akshare at import time)."""
    global _AK
    if _AK is None:
        import akshare as m
        _AK = m
    return _AK


def _ensure_browser_ua() -> None:
    """Patch requests' default UA to a browser UA (idempotent).

    East Money closes connections when requests advertises
    ``python-requests/x.y.z``; a browser UA keeps the akshare wrappers alive.
    """
    import requests.utils
    if getattr(requests.utils.default_user_agent, "_finkit_patched", False):
        return

    def _patched() -> str:
        return _BROWSER_UA

    _patched._finkit_patched = True  # type: ignore[attr-defined]
    requests.utils.default_user_agent = _patched


_ensure_browser_ua()


def _returns_from_closes(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Daily returns from (date, close) pairs; the first row has no return."""
    out: list[tuple[str, float]] = []
    for i in range(1, len(pairs)):
        prev = pairs[i - 1][1]
        if prev and prev > 0:
            out.append((pairs[i][0], pairs[i][1] / prev - 1.0))
    return out


def _df_series(df, date_col: str, value_col: str) -> list[tuple[str, float]]:
    """(date, value) pairs from a DataFrame row by row, dropping NaN values."""
    import pandas as pd
    out: list[tuple[str, float]] = []
    for _, row in df.iterrows():
        v = row[value_col]
        if pd.isna(v):
            continue
        out.append((str(row[date_col]), float(v)))
    return sorted(out, key=lambda x: x[0])


# --------------------------------------------------------------------------- #
# index wrappers
# --------------------------------------------------------------------------- #

_INDEX_KLINE_COLUMNS = [
    "日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率",
]

# 全球指数中文名 -> 东财 secid（push2his 全球市场前缀 100）
_GLOBAL_INDEX_SECIDS = {
    "日经225": "100.N225",
    "德国DAX30": "100.GDAXI",
    "恒生指数": "100.HSI",
}


def _em_kline_closes(secid: str) -> list[tuple[str, float]]:
    """East Money push2his kline, full history in one call -> [(date, close)].

    Uses the exact parameter set verified live (no ``ut`` token, ``fqt=1``,
    ``beg=0``, browser UA + quote-page Referer); the variant with ``ut`` and
    ``beg=YYYYMMDD`` gets connections reset by the CDN.
    """
    import requests

    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101",
        "fqt": "1",
        "beg": "0",
        "end": "20500101",
    }
    r = requests.get(
        _EASTMONEY_KLINE_URL, params=params,
        headers={"User-Agent": _BROWSER_UA, "Referer": "https://quote.eastmoney.com/"},
        timeout=30,
    )
    r.raise_for_status()
    klines = (r.json().get("data") or {}).get("klines") or []
    out: list[tuple[str, float]] = []
    for row in klines:
        parts = row.split(",")
        if len(parts) < 3:
            continue
        try:
            out.append((parts[0][:10], float(parts[2])))
        except ValueError:
            continue
    return out


def _tencent_kline_closes(tx_code: str, max_pages: int = 30) -> list[tuple[str, float]]:
    """Tencent kline 接口 (web.ifzq.gtimg.cn) 翻页拉全历史。

    用 ``kline/kline``（end 参数生效），而非 ``fqkline/get``（end 被忽略）。
    每次把 ``end`` 设为上次返回最旧日期的前一天，直到返回空页/无新行/不足 640 行。
    """
    import datetime
    import requests

    collected: dict[str, float] = {}
    end = datetime.date.today().isoformat()
    for _ in range(max_pages):
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
               f"?param={tx_code},day,,{end},640")
        r = requests.get(url, timeout=30, headers={"Referer": "https://gu.qq.com/"})
        r.raise_for_status()
        rows = (r.json().get("data", {}).get(tx_code, {}) or {}).get("day") or []
        if not rows:
            break
        new = 0
        for row in rows:
            d = row[0][:10]
            try:
                if d not in collected:
                    collected[d] = float(row[2])
                    new += 1
            except (ValueError, IndexError):
                continue
        oldest = rows[0][0][:10]
        if new == 0 or len(rows) < 640:
            break
        end = (datetime.date.fromisoformat(oldest) - datetime.timedelta(days=1)).isoformat()
    return sorted(collected.items())


def _a_share_secid(code: str) -> str:
    """A股指数代码 -> 东财 secid：399xxx 深市前缀 0.，其余沪市前缀 1.。"""
    return f"0.{code}" if code.startswith("399") else f"1.{code}"


def _a_share_tx_code(code: str) -> str:
    """A股指数代码 -> 腾讯代码：399xxx 前缀 sz，其余前缀 sh。"""
    return f"sz{code}" if code.startswith("399") else f"sh{code}"


def _index_kline_direct(code: str, begin: str, end: str):
    """Direct East Money kline fetch — akshare's index_zh_a_hist bypass.

    Mirrors akshare's exact params/columns; used only when
    ``ak.index_zh_a_hist`` cannot reach its symbol map endpoint
    (``80.push2.eastmoney.com`` blocked).  Tries market prefixes 1./0./2./47.
    """
    import pandas as pd
    import requests

    last_exc: Optional[Exception] = None
    for market in ("1.", "0.", "2.", "47."):
        params = {
            "secid": f"{market}{code}",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "0",
            "beg": begin,
            "end": end,
        }
        try:
            r = requests.get(
                _EASTMONEY_KLINE_URL, params=params,
                headers={"User-Agent": _BROWSER_UA}, timeout=20,
            )
            data = r.json()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            continue
        klines = (data.get("data") or {}).get("klines") or []
        if klines:
            rows = [row.split(",") for row in klines]
            return pd.DataFrame(rows, columns=_INDEX_KLINE_COLUMNS)
    if last_exc is not None:
        raise last_exc
    return pd.DataFrame()


def fetch_index_pct(code: str) -> list[tuple[str, float]]:
    """A股指数日收益。三级回退：akshare → 东财直连 → 腾讯翻页。

    akshare 走 index_zh_a_hist（依赖 80.push2 符号表，常被拒）；
    东财直连 push2his 一次拉全历史；腾讯按 640 行/页回翻 kline/kline。
    任一源抛错或返回空，**绝不**向上抛——直接试下一个，保证最后一站
    失败才 NoDataError/raise。
    """
    today = date.today()
    begin = (today - timedelta(days=5 * 365)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    try:
        ak = _ak()
        df = ak.index_zh_a_hist(symbol=code, period="daily", start_date=begin, end_date=end)
        if df is None or df.empty or "涨跌幅" not in df.columns:
            df = _index_kline_direct(code, begin, end)
        if df is not None and not df.empty and "涨跌幅" in df.columns:
            import pandas as pd
            out = []
            for _, row in df.iterrows():
                v = row["涨跌幅"]
                if not pd.isna(v):
                    out.append((str(row["日期"]), float(v) / 100.0))
            if out:
                return out
    except Exception:  # noqa: BLE001 — fall through to direct sources
        pass

    try:
        closes = _em_kline_closes(_a_share_secid(code))
        if closes:
            return _returns_from_closes(closes)
    except Exception:  # noqa: BLE001
        pass

    closes = _tencent_kline_closes(_a_share_tx_code(code))
    return _returns_from_closes(closes)


def fetch_index_pct_sw(code: str) -> list[tuple[str, float]]:
    """申万一级行业指数日收益 —— 收盘价自行计算，首行跳过。"""
    ak = _ak()
    df = ak.index_hist_sw(symbol=code, period="day")
    if df is None or df.empty:
        return []
    return _returns_from_closes(_df_series(df, "日期", "收盘"))


def fetch_index_pct_us(symbol: str) -> list[tuple[str, float]]:
    """美股指数日收益（新浪）—— close 自行计算，首行跳过。"""
    ak = _ak()
    df = ak.index_us_stock_sina(symbol=symbol)
    if df is None or df.empty:
        return []
    return _returns_from_closes(_df_series(df, "date", "close"))


def fetch_index_pct_global(name_cn: str) -> list[tuple[str, float]]:
    """全球指数日收益。回退链：akshare → 东财直连(secid 映射) → 腾讯(仅港股)。

    akshare 的 index_global_hist_em 依赖 py_mini_racer(V8) 计算东财加密参数，
    并发初始化会崩溃且东财连接常被拒；直连 push2his 无需 V8，全历史一次返回。
    任一源抛错或返回空都试下一个，全部失败才 raise NoDataError。
    """
    try:
        ak = _ak()
        df = ak.index_global_hist_em(symbol=name_cn)
        if df is not None and not df.empty:
            return _returns_from_closes(_df_series(df, "日期", "最新价"))
    except Exception:  # noqa: BLE001 — V8 crash / connection refused: fall through
        pass

    secid = _GLOBAL_INDEX_SECIDS.get(name_cn)
    if secid:
        try:
            closes = _em_kline_closes(secid)
            if closes:
                return _returns_from_closes(closes)
        except Exception:  # noqa: BLE001
            pass

    if name_cn == "恒生指数":
        try:
            closes = _tencent_kline_closes("hkHSI")
            if closes:
                return _returns_from_closes(closes)
        except Exception:  # noqa: BLE001
            pass

    raise NoDataError(f"全球指数 {name_cn} 所有数据源均未取到数据")


# --------------------------------------------------------------------------- #
# rates / yields
# --------------------------------------------------------------------------- #

def fetch_cn_us_yields():
    """中美国债收益率原始 DataFrame（调用方自选列）。"""
    ak = _ak()
    return ak.bond_zh_us_rate(start_date="19901219")


def fetch_china_yield(
    curve_name: str,
    tenor: str,
    start_year: int,
    end_year: Optional[int] = None,
) -> list[tuple[str, float]]:
    """中债收益率曲线（bond_china_yield）按年循环（单窗 <1 年）。

    曲线名如 "中债国债收益率曲线" / "中债中短期票据收益率曲线(AAA)"；
    tenor 如 "3月"。返回 date->yield（%）。
    """
    ak = _ak()
    import pandas as pd
    now_year = date.today().year
    end_year = max(start_year, min(end_year if end_year else now_year, now_year))
    out: list[tuple[str, float]] = []
    for y in range(start_year, end_year + 1):
        try:
            df = ak.bond_china_yield(start_date=f"{y}0101", end_date=f"{y}1231")
        except Exception:  # noqa: BLE001 — one broken year must not kill the series
            continue
        if df is None or df.empty or tenor not in df.columns:
            continue
        sub = df[df["曲线名称"].astype(str) == curve_name]
        for _, row in sub.iterrows():
            v = row[tenor]
            if pd.isna(v):
                continue
            out.append((str(row["日期"]), float(v)))
    if not out:
        return []
    dedup: dict[str, float] = {}
    for d, v in out:
        dedup[d] = v
    return sorted(dedup.items())


# --------------------------------------------------------------------------- #
# macro
# --------------------------------------------------------------------------- #

def fetch_rmb_mid(item: str = "美元/人民币_中间价") -> list[tuple[str, float]]:
    """美元/人民币中间价（macro_china_rmb，无参，日频）。返回 date->level。"""
    ak = _ak()
    df = ak.macro_china_rmb()
    if df is None or df.empty:
        return []
    if item not in df.columns:
        raise NoDataError(f"macro_china_rmb 无列 {item}；实际列: {list(df.columns)}")
    return _df_series(df, "日期", item)


def fetch_macro_monthly(func_name: str, item: str) -> list[tuple[str, float]]:
    """金十宏观月/季数据（macro_china_cpi_monthly / macro_china_pmi_yearly）。

    列：商品/日期/今值/预测值/前值。按 商品==item 过滤，带容错回退：
    精确匹配 -> 子串匹配 -> 若输出仅一个序列则采用之。
    """
    ak = _ak()
    fn = getattr(ak, func_name, None)
    if fn is None:
        raise ValueError(f"akshare 无函数 {func_name}")
    df = fn()
    if df is None or df.empty:
        return []
    if "商品" not in df.columns or "今值" not in df.columns:
        raise NoDataError(f"{func_name} 输出列不符合预期: {list(df.columns)}")
    sub = df[df["商品"].astype(str) == item]
    if sub.empty:
        sub = df[df["商品"].astype(str).str.contains(item, regex=False, na=False)]
    if sub.empty and df["商品"].nunique() == 1:
        sub = df
    if sub.empty:
        return []
    return _df_series(sub, "日期", "今值")


# --------------------------------------------------------------------------- #
# alpha flows
# --------------------------------------------------------------------------- #

def fetch_northbound() -> list[tuple[str, float]]:
    """北向资金每日净流入（亿元）。接口仅返回当日快照 -> NoDataError。"""
    ak = _ak()
    import pandas as pd
    df = ak.stock_hsgt_fund_flow_summary_em()
    if df is None or df.empty:
        return []
    days = sorted(df["交易日"].astype(str).unique())
    if len(days) <= 1:
        raise NoDataError(
            f"北向资金接口仅返回当日快照（交易日 {days[0] if days else '?'}），"
            "无法构成历史序列"
        )
    out: list[tuple[str, float]] = []
    for d in days:
        sub = df[(df["交易日"].astype(str) == d) & (df["资金方向"] == "北向")]
        val = float(pd.to_numeric(sub["资金净流入"], errors="coerce").sum())
        out.append((d, val))
    return sorted(out)


def fetch_margin_szse(years: int = 2) -> list[tuple[str, float]]:
    """深市融资融券余额逐日循环（stock_margin_szse）。近 N 年交易日。

    周末/节假日按日抛错 -> 捕获继续；失败率 > 50% 抛 NoDataError。
    """
    ak = _ak()
    import pandas as pd
    today = date.today()
    start = today - timedelta(days=years * 365)
    out: list[tuple[str, float]] = []
    fails = 0
    total = 0
    d = start
    while d <= today:
        if d.weekday() < 5:
            total += 1
            try:
                df = ak.stock_margin_szse(date=d.strftime("%Y%m%d"))
                if df is not None and len(df) and "融资融券余额" in df.columns:
                    val = float(pd.to_numeric(df["融资融券余额"], errors="coerce").sum())
                    out.append((d.isoformat(), val))
                else:
                    fails += 1
            except Exception:  # noqa: BLE001 — holidays/weekends error per-date
                fails += 1
        d += timedelta(days=1)
    if total and fails > total * 0.5:
        raise NoDataError(f"stock_margin_szse 失败率过高（{fails}/{total} 日期失败）")
    if not out:
        raise NoDataError("stock_margin_szse 无数据")
    return sorted(out)


def fetch_moneyflow_sum() -> list[tuple[str, float]]:
    """全市场个股主力净流入合计（今日快照）-> 当日单点序列。

    仅当日截面，历史由 factor_sync 的 JSON sidecar 累积后再跑 flow_zscore。
    列名来自 akshare 1.18.88 源码（"今日主力净流入-净额"，单位为亿元）。
    """
    ak = _ak()
    import pandas as pd
    df = ak.stock_individual_fund_flow_rank(indicator="今日")
    if df is None or df.empty:
        return []
    col = "今日主力净流入-净额"
    if col not in df.columns:
        raise NoDataError(
            f"stock_individual_fund_flow_rank 无列 {col}；实际列: {list(df.columns)}"
        )
    total = float(pd.to_numeric(df[col], errors="coerce").sum())
    return [(date.today().isoformat(), total)]
