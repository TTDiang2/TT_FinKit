"""Market-data middleware — ONE facade for all daily close/return fetches.

数据源中间件：akshare / 东财 push2his / 腾讯 ifzq / yfinance 统一为一个调用口。

职责（factor_sources 等调用方不再关心具体数据源）:
  - provider 注册与回退链：按优先级逐个尝试，第一个非空结果胜出
  - 每 provider 超时保护（线程池 wait_for，防单源挂死拖垮整链）
  - 拉取报告（哪个 symbol 最后由哪个源服务 / 哪些源失败）供调试

Provider 协议: Callable[[str], list[tuple[str, float]]]  # symbol -> [(date, close)]
异常约定: provider 抛任何异常 = 该源不可用，middleware 捕获后试下一源。
"""
from __future__ import annotations

import queue
import threading
from datetime import date, timedelta
from typing import Callable

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

# 每个 provider 的硬超时（秒）；整链最坏 = 链长 × 该值
_PROVIDER_TIMEOUT_S = 60

# (symbol -> 最后成功服务的 provider 名)；读多写少，锁保护并发 sync
_LAST_PROVIDER: dict[str, str] = {}
_LOCK = threading.Lock()


def _ensure_browser_ua() -> None:
    """Patch requests' default UA to a browser UA (idempotent)."""
    import requests.utils
    if getattr(requests.utils.default_user_agent, "_finkit_patched", False):
        return

    def _patched() -> str:
        return _BROWSER_UA

    _patched._finkit_patched = True  # type: ignore[attr-defined]
    requests.utils.default_user_agent = _patched


_ensure_browser_ua()


# --------------------------------------------------------------------------- #
# Providers — each returns [(date_str, close)] or raises
# --------------------------------------------------------------------------- #

def _p_eastmoney_index(code: str) -> list[tuple[str, float]]:
    """东财 push2his 直连：A股指数全历史。secid: 399xxx→0. 其余→1."""
    secid = f"0.{code}" if code.startswith("399") else f"1.{code}"
    return _em_kline_closes(secid)


def _p_tencent_index(code: str) -> list[tuple[str, float]]:
    """腾讯 ifzq 翻页：A股指数。tx code: 399xxx→sz 其余→sh."""
    tx = f"sz{code}" if code.startswith("399") else f"sh{code}"
    return _tencent_kline_closes(tx)


def _p_akshare_index(code: str) -> list[tuple[str, float]]:
    """akshare index_zh_a_hist → 收盘价序列（首行无收益，仅返回 close）。"""
    import akshare as ak
    today = date.today()
    df = ak.index_zh_a_hist(
        symbol=code, period="daily",
        start_date=(today - timedelta(days=5 * 365)).strftime("%Y%m%d"),
        end_date=today.strftime("%Y%m%d"),
    )
    if df is None or df.empty or "收盘" not in df.columns:
        return []
    return [
        (str(row["日期"])[:10], float(row["收盘"]))
        for _, row in df.iterrows()
        if row["收盘"] == row["收盘"]
    ]


# yfinance symbol 映射：全球指数中文名 / A股代码 / 美股代码
_YF_GLOBAL: dict[str, str] = {
    "日经225": "^N225",
    "德国DAX30": "^GDAXI",
    "恒生指数": "^HSI",
    "道琼斯": "^DJI",
    "纳斯达克": "^IXIC",
    "标普500": "^GSPC",
}


def yf_symbol_for(code_or_name: str) -> str | None:
    """code/name → yfinance symbol；无法映射返回 None。"""
    if code_or_name in _YF_GLOBAL:
        return _YF_GLOBAL[code_or_name]
    if code_or_name.startswith("399"):
        return f"{code_or_name}.SZ"
    if code_or_name.isdigit() and len(code_or_name) == 6:
        return f"{code_or_name}.SS"
    if code_or_name.startswith("^") or "." in code_or_name:
        return code_or_name
    return None


def _p_yfinance(code_or_name: str) -> list[tuple[str, float]]:
    """yfinance 日收盘（全球指数/A股/美股通用兜底）。未安装/无映射直接抛。"""
    import yfinance as yf
    sym = yf_symbol_for(code_or_name)
    if not sym:
        raise ValueError(f"yfinance: 无法映射 {code_or_name}")
    tk = yf.Ticker(sym)
    df = tk.history(period="10y", interval="1d", auto_adjust=False)
    if df is None or df.empty:
        return []
    out = []
    for idx, v in df["Close"].items():
        if v != v:  # NaN
            continue
        d = idx.strftime("%Y-%m-%d")
        out.append((d, float(v)))
    return sorted(out)


# --------------------------------------------------------------------------- #
# Low-level fetchers (moved from factor_sources, unchanged behavior)
# --------------------------------------------------------------------------- #

def _em_kline_closes(secid: str) -> list[tuple[str, float]]:
    """East Money push2his kline, full history in one call -> [(date, close)]."""
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
    """腾讯 kline/kline 翻页拉全历史（end 参数生效）。"""
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


# --------------------------------------------------------------------------- #
# Named chains — 调用方按业务语义选链，不感知具体源
# --------------------------------------------------------------------------- #

CHAIN_CN_INDEX: list[tuple[str, Callable[[str], list[tuple[str, float]]]]] = [
    ("eastmoney", _p_eastmoney_index),
    ("tencent", _p_tencent_index),
    ("akshare", _p_akshare_index),
    ("yfinance", _p_yfinance),
]

_CHAIN_GLOBAL_NAME_TO_SECID = {
    "日经225": "100.N225",
    "德国DAX30": "100.GDAXI",
    "恒生指数": "100.HSI",
}


def _p_eastmoney_global(name_cn: str) -> list[tuple[str, float]]:
    secid = _CHAIN_GLOBAL_NAME_TO_SECID.get(name_cn)
    if not secid:
        return []
    return _em_kline_closes(secid)


def _p_tencent_hsi(name_cn: str) -> list[tuple[str, float]]:
    if name_cn != "恒生指数":
        return []
    return _tencent_kline_closes("hkHSI")


CHAIN_GLOBAL: list[tuple[str, Callable[[str], list[tuple[str, float]]]]] = [
    ("eastmoney", _p_eastmoney_global),
    ("tencent", _p_tencent_hsi),
    ("yfinance", _p_yfinance),
]

def _p_sina_us(symbol: str) -> list[tuple[str, float]]:
    """akshare 新浪美股指数 → close 序列。"""
    import akshare as ak
    df = ak.index_us_stock_sina(symbol=symbol)
    if df is None or df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        v = row.get("close")
        d = row.get("date")
        if v == v and d is not None:
            out.append((str(d)[:10], float(v)))
    return sorted(out)


CHAIN_US: list[tuple[str, Callable[[str], list[tuple[str, float]]]]] = [
    ("sina-akshare", _p_sina_us),
    ("yfinance", _p_yfinance),
]


CHAINS: dict[str, list[tuple[str, Callable[[str], list[tuple[str, float]]]]]] = {
    "cn_index": CHAIN_CN_INDEX,
    "global": CHAIN_GLOBAL,
    "us": CHAIN_US,
}


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #

def fetch_closes(code: str, chain: str = "cn_index") -> list[tuple[str, float]]:
    """按命名回退链拉日收盘价。全链失败抛 RuntimeError（含各源失败原因摘要）。

    每个 provider 在 daemon 线程中执行（超时即弃，不阻塞整链；daemon 线程
    也不会拖住进程退出）。
    """
    providers = CHAINS[chain]
    errors: list[str] = []
    for pname, fn in providers:
        q: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=1)

        def _run(fn=fn, code=code, q=q) -> None:
            try:
                q.put(("ok", fn(code)))
            except BaseException as e:  # noqa: BLE001 — 单源失败不阻断回退
                q.put(("err", e))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        try:
            status, payload = q.get(timeout=_PROVIDER_TIMEOUT_S)
        except queue.Empty:
            errors.append(f"{pname}: timeout>{_PROVIDER_TIMEOUT_S}s")
            continue
        if status == "ok" and payload:
            with _LOCK:
                _LAST_PROVIDER[code] = pname
            return payload  # type: ignore[return-value]
        if status == "ok":
            errors.append(f"{pname}: empty")
        else:
            errors.append(f"{pname}: {type(payload).__name__}: {payload}")
    raise RuntimeError(f"所有数据源均失败 [{code}] chain={chain} :: {'; '.join(errors)}")


def fetch_returns(code: str, chain: str = "cn_index") -> list[tuple[str, float]]:
    """日收益序列（首行跳过）。"""
    closes = fetch_closes(code, chain)
    out: list[tuple[str, float]] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1][1]
        if prev and prev > 0:
            out.append((closes[i][0], closes[i][1] / prev - 1.0))
    return out


def last_provider_report() -> dict[str, str]:
    """{symbol: 最后成功服务的 provider} — 调试/健康检查用。"""
    with _LOCK:
        return dict(_LAST_PROVIDER)
