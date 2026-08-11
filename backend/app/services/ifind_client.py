"""iFinDPy (同花顺 quantapi) thin async wrapper.

iFinDPy is a globally-singleton, synchronous, login-gated client. Key facts:
- THS_iFinDLogin(user,pwd) -> int errorcode (0=ok, -201=already logged in, -2=bad creds)
- Login is mutually exclusive: only one live session per account at a time,
  and it is process-wide (not per-coroutine). We therefore cache the logged-in
  username and only re-login when credentials change.
- THS_RQ / THS_HQ return THSData objects with attributes:
    .errorcode (0=ok), .errmsg, .data (pandas DataFrame by default),
    .time (list of date strings), .thscode (list)

All iFinDPy calls are blocking (login timeout up to 90s) -> every call is
wrapped in asyncio.to_thread so the FastAPI event loop is never stalled.

This module never raises on iFinDPy import failure — the caller decides
whether to degrade gracefully (e.g. fall back to Tencent quotes).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user_settings import UserSettings
from ..utils.crypto import decrypt_field


class IFindError(RuntimeError):
    """Raised when an iFinD operation fails (login, query, parse)."""


# --------------------------------------------------------------------------- #
# Process-wide login state (iFinD sessions are globally exclusive)
# --------------------------------------------------------------------------- #

_login_lock = threading.RLock()
_logged_in_user: Optional[str] = None
_ifind_import_error: Optional[Exception] = None

try:
    import iFinDPy  # noqa: F401  (imported for side-effect: loads the native lib)
except Exception as _e:  # pragma: no cover - environment-dependent
    iFinDPy = None  # type: ignore
    _ifind_import_error = _e


def is_available() -> bool:
    """True when the iFinDPy package could be imported on this machine."""
    return iFinDPy is not None


def import_error() -> Optional[str]:
    return str(_ifind_import_error) if _ifind_import_error else None


# --------------------------------------------------------------------------- #
# Code format conversion: (symbol, exchange) -> iFinD thscode
# --------------------------------------------------------------------------- #

def to_thscode(symbol: str, exchange: str) -> str:
    ex = (exchange or "").upper().strip()
    sym = (symbol or "").strip()
    if ex == "SH":
        return f"{sym}.SH"
    if ex == "SZ":
        return f"{sym}.SZ"
    if ex == "HK":
        return f"{sym}.HK"
    if ex == "FUND_CN":
        # Open-end funds use the .OF suffix in iFinD
        return f"{sym}.OF"
    if ex == "US":
        # US tickers: iFinD auto-resolves market; common form is AAPL or AAPL.O
        return sym
    return sym


def supports_exchange(exchange: str) -> bool:
    """Whether iFinD can serve this market (used to decide fallback)."""
    return (exchange or "").upper() in ("SH", "SZ", "HK", "FUND_CN", "US")


# --------------------------------------------------------------------------- #
# Credential lookup helper
# --------------------------------------------------------------------------- #

async def get_credentials(db: AsyncSession, user_id: str) -> tuple[str, str]:
    """Return (username, password) for the user, or ('','') if not configured.

    The password is stored encrypted — we decrypt here for use by iFinD login.
    """
    res = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    s = res.scalar_one_or_none()
    if not s:
        return ("", "")
    return (s.ifind_username or "", decrypt_field(s.ifind_password or ""))


# --------------------------------------------------------------------------- #
# Synchronous iFinD operations (run via asyncio.to_thread)
# --------------------------------------------------------------------------- #

def _login_sync(username: str, password: str) -> None:
    global _logged_in_user
    if iFinDPy is None:
        raise IFindError(f"iFinDPy 不可用: {import_error() or '未安装'}")
    with _login_lock:
        # Already logged in as the same user -> nothing to do
        if _logged_in_user == username and _logged_in_user is not None:
            return
        # Switching accounts -> log out the previous session first
        if _logged_in_user is not None:
            try:
                iFinDPy.THS_iFinDLogout()
            except Exception:
                pass
            _logged_in_user = None
        rc = iFinDPy.THS_iFinDLogin(username, password)
        # 0 = success, -201 = already logged in (treat as success)
        if rc not in (0, -201):
            err = ""
            try:
                if hasattr(iFinDPy, "THS_GetErrorInfo"):
                    err = str(iFinDPy.THS_GetErrorInfo(rc, ""))
            except Exception:
                pass
            hint = {-2: "用户名或密码错误"}.get(rc, "")
            raise IFindError(f"iFinD 登录失败 (code={rc}){': ' + hint if hint else ''}{(' — ' + err) if err else ''}")
        _logged_in_user = username


def _realtime_sync(thscode: str) -> tuple[float, str]:
    """Return (latest_price, security_name). Raises IFindError on failure."""
    if iFinDPy is None:
        raise IFindError("iFinDPy 不可用")
    # 场外开放式基金 (.OF): 无日内实时成交价，取最新公布的单位净值 (THS_BD)
    if thscode.endswith(".OF"):
        d = iFinDPy.THS_BD(thscode, "ths_unit_nv_fund", "")
        if getattr(d, "errorcode", -1) != 0:
            raise IFindError(f"THS_BD error {getattr(d,'errorcode','?')}: {getattr(d,'errmsg','')}")
        price = 0.0
        df = getattr(d, "data", None)
        try:
            if df is not None and hasattr(df, "iloc") and len(df) > 0:
                v = df.iloc[0, -1]
                if v is not None and v == v:  # NaN guard
                    price = float(v)
        except (TypeError, ValueError):
            pass
        if price <= 0:
            raise IFindError(f"THS_BD: 未取到有效单位净值 ({thscode})")
        return price, ""
    # 股票/ETF/HK: latest = most recent traded price; ths_stock_short_name_stock = CN name
    d = iFinDPy.THS_RQ(thscode, "latest;ths_stock_short_name_stock", "")
    if getattr(d, "errorcode", -1) != 0:
        raise IFindError(f"THS_RQ error {getattr(d,'errorcode','?')}: {getattr(d,'errmsg','')}")
    price = 0.0
    name = ""
    df = getattr(d, "data", None)
    try:
        import pandas as _pd  # noqa: F401
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            row = df.iloc[0]
            for key in ("latest", "close"):
                if key in df.columns:
                    try:
                        price = float(row[key])
                        break
                    except (TypeError, ValueError):
                        pass
            if "ths_stock_short_name_stock" in df.columns:
                try:
                    name = str(row["ths_stock_short_name_stock"] or "")
                except Exception:
                    pass
    except Exception:
        pass
    if price <= 0:
        raise IFindError(f"THS_RQ: 未取到有效最新价 ({thscode})")
    return price, name


def _history_close_sync(thscode: str, begin: str, end: str) -> list[dict]:
    """Return list of {date, close} for the daily close series. Raises IFindError."""
    if iFinDPy is None:
        raise IFindError("iFinDPy 不可用")
    # 场外开放式基金 (.OF): 用 THS_DS 取日度单位净值序列（基金 T+1 公布净值，无日内行情）
    if thscode.endswith(".OF"):
        d = iFinDPy.THS_DS(thscode, "ths_unit_nv_fund", "", "", begin, end)
        if getattr(d, "errorcode", -1) != 0:
            raise IFindError(f"THS_DS error {getattr(d,'errorcode','?')}: {getattr(d,'errmsg','')}")
        out: list[dict] = []
        df = getattr(d, "data", None)
        times = list(getattr(d, "time", []) or [])
        closes: list = []
        if df is not None and hasattr(df, "columns"):
            nav_col = None
            for col in df.columns:
                if "ths_unit_nv_fund" in str(col):
                    nav_col = col
                    break
            if nav_col is None and len(df.columns) >= 1:
                nav_col = df.columns[-1]
            if nav_col is not None:
                closes = list(df[nav_col])
            if not times and getattr(df, "index", None) is not None:
                times = list(df.index)
        n = min(len(times), len(closes))
        for i in range(n):
            c = closes[i]
            if c is None:
                continue
            try:
                cf = float(c)
            except (TypeError, ValueError):
                continue
            if cf != cf or cf <= 0:  # NaN + non-positive guard
                continue
            ds = str(times[i])[:10] if times[i] else ""
            if not ds:
                continue
            out.append({"date": ds, "close": round(cf, 6)})
        if not out:
            raise IFindError(f"THS_DS: 区间无有效净值 ({thscode}, {begin}~{end})")
        return out
    # 股票/ETF/HK: CPS:1 = unadjusted (raw traded prices). We use unadjusted so
    # the curve reflects the real prices the user traded at; cost basis lines up
    # with recorded buy/sell unit prices.
    d = iFinDPy.THS_HQ(thscode, "close", "CPS:1", begin, end)
    if getattr(d, "errorcode", -1) != 0:
        raise IFindError(f"THS_HQ error {getattr(d,'errorcode','?')}: {getattr(d,'errmsg','')}")
    dates: list = list(getattr(d, "time", []) or [])
    closes: list = []
    df = getattr(d, "data", None)
    try:
        import pandas as _pd  # noqa: F401
        if df is not None and hasattr(df, "columns"):
            if "close" in df.columns:
                closes = list(df["close"])
            elif len(df.columns) >= 1:
                closes = list(df.iloc[:, 0])
            # If dates empty, fall back to the DataFrame index
            if not dates and getattr(df, "index", None) is not None:
                dates = list(df.index)
    except Exception:
        pass

    out: list[dict] = []
    n = min(len(dates), len(closes))
    for i in range(n):
        c = closes[i]
        if c is None:
            continue
        try:
            cf = float(c)
        except (TypeError, ValueError):
            continue
        if cf != cf or cf <= 0:  # NaN guard + non-positive guard
            continue
        ds = str(dates[i])[:10] if dates[i] else ""
        if not ds:
            continue
        out.append({"date": ds, "close": round(cf, 6)})
    if not out:
        raise IFindError(f"THS_HQ: 区间无有效收盘价 ({thscode}, {begin}~{end})")
    return out


# --------------------------------------------------------------------------- #
# Fund-specific paths (.OF open-end funds use different iFinD interfaces)
#   Stock/ETF fields (THS_RQ latest / THS_HQ close) return -4001 no_data for .OF
#   Fund unit NAV lives under the ths_unit_nv_fund indicator and must be queried
#   via THS_BD (latest snapshot) / THS_DS (daily date series). Verified at the
#   Task0 命门 check for 000217/004243/110001/017895.OF.
# --------------------------------------------------------------------------- #

def _fund_nav_latest_sync(thscode: str) -> tuple[float, str]:
    """Return (latest_unit_nav, fund_name) for an open-end fund (.OF).

    Uses THS_BD with the ths_unit_nv_fund indicator. The fund short name is
    not fetched here — callers already hold investment.name from the DB and
    we keep this call to a single verified indicator.
    """
    if iFinDPy is None:
        raise IFindError("iFinDPy 不可用")
    d = iFinDPy.THS_BD(thscode, "ths_unit_nv_fund", "")
    if getattr(d, "errorcode", -1) != 0:
        raise IFindError(f"THS_BD error {getattr(d,'errorcode','?')}: {getattr(d,'errmsg','')}")
    nav = 0.0
    df = getattr(d, "data", None)
    try:
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            row = df.iloc[0]
            if "ths_unit_nv_fund" in df.columns:
                try:
                    nav = float(row["ths_unit_nv_fund"])
                except (TypeError, ValueError):
                    pass
            elif len(df.columns) >= 1:
                # Fallback: first numeric column
                try:
                    nav = float(row.iloc[0])
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    if nav <= 0:
        raise IFindError(f"THS_BD: 未取到有效单位净值 ({thscode})")
    return nav, ""


def _fund_nav_history_sync(thscode: str, begin: str, end: str) -> list[dict]:
    """Return list of {date, close} for a fund's daily unit NAV series.

    Uses THS_DS with the ths_unit_nv_fund indicator. ``close`` in each entry is
    the unit NAV (not a traded price) — downstream consumers treat it
    identically to a price series.
    """
    if iFinDPy is None:
        raise IFindError("iFinDPy 不可用")
    # THS_DS(thscode, jsonIndicator, jsonparam, globalparam, begintime, endtime)
    d = iFinDPy.THS_DS(thscode, "ths_unit_nv_fund", "", "", begin, end)
    if getattr(d, "errorcode", -1) != 0:
        raise IFindError(f"THS_DS error {getattr(d,'errorcode','?')}: {getattr(d,'errmsg','')}")
    dates: list = list(getattr(d, "time", []) or [])
    navs: list = []
    df = getattr(d, "data", None)
    try:
        if df is not None and hasattr(df, "columns"):
            if "ths_unit_nv_fund" in df.columns:
                navs = list(df["ths_unit_nv_fund"])
            elif "close" in df.columns:
                navs = list(df["close"])
            elif len(df.columns) >= 1:
                navs = list(df.iloc[:, 0])
            if not dates and getattr(df, "index", None) is not None:
                dates = list(df.index)
    except Exception:
        pass

    out: list[dict] = []
    n = min(len(dates), len(navs))
    for i in range(n):
        v = navs[i]
        if v is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if vf != vf or vf <= 0:  # NaN guard + non-positive guard
            continue
        ds = str(dates[i])[:10] if dates[i] else ""
        if not ds:
            continue
        out.append({"date": ds, "close": round(vf, 6)})
    if not out:
        raise IFindError(f"THS_DS: 区间无有效净值 ({thscode}, {begin}~{end})")
    return out


# --------------------------------------------------------------------------- #
# Async API (the public surface used by routers / price_provider)
# --------------------------------------------------------------------------- #

async def ensure_logged_in(username: str, password: str) -> None:
    if not username or not password:
        raise IFindError("iFinD 凭证未配置")
    await asyncio.to_thread(_login_sync, username, password)


async def fetch_realtime(username: str, password: str, symbol: str, exchange: str) -> dict:
    """Return {price, name, source, thscode, currency}. Raises IFindError."""
    await ensure_logged_in(username, password)
    thscode = to_thscode(symbol, exchange)
    ex = (exchange or "").upper()
    if ex == "FUND_CN":
        price, name = await asyncio.to_thread(_fund_nav_latest_sync, thscode)
    else:
        price, name = await asyncio.to_thread(_realtime_sync, thscode)
    currency = "HKD" if ex == "HK" else ("USD" if ex == "US" else "CNY")
    return {"price": price, "name": name, "source": "ifind", "thscode": thscode, "currency": currency}


async def fetch_history_close(
    username: str, password: str, symbol: str, exchange: str, begin: str, end: str
) -> list[dict]:
    """Return list of {date, close}. Raises IFindError."""
    await ensure_logged_in(username, password)
    thscode = to_thscode(symbol, exchange)
    if (exchange or "").upper() == "FUND_CN":
        return await asyncio.to_thread(_fund_nav_history_sync, thscode, begin, end)
    return await asyncio.to_thread(_history_close_sync, thscode, begin, end)
