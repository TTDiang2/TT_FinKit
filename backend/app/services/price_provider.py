"""Price providers for live market data.

We use Tencent Finance (qt.gtimg.cn) as the single source. Response format:

  v_sh600519="1~贵州茅台~600519~1185.49~..."     # A-share SH
  v_sz000001="51~平安银行~000001~10.05~..."      # A-share SZ
  v_hk00700="100~腾讯控股~00700~429.800~..."    # HK stock
  v_usAAPL="200~Apple~AAPL.OQ~281.74~..."      # US stock (USD)

  Field 0 = market type code (1=SH A-share, 51=SZ A-share, 100=HK, 200=US)
  Field 1 = name (Chinese for CN, English for HK/US)
  Field 2 = symbol (raw)
  Field 3 = current price (CNY / HKD / USD depending on market)

Supported (auto-refresh): SH, SZ, FUND_CN, HK.
Unsupported (manual entry only): US, CRYPTO — Tencent aggressively throttles
  US queries per IP, with cooldown windows that exceed any practical
  user-facing retry loop. For these, users enter current_price manually.
"""
from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

# --------------------------------------------------------------------------- #
# In-memory TTL cache + last-request throttle
# --------------------------------------------------------------------------- #
# Tencent throttles per IP — repeated calls within a few seconds may return
# `pv_none_match="1"`. We cache successful quotes for 60s and add a small
# spacing delay between calls.

import time as _time
import threading as _threading
import asyncio as _asyncio

_CACHE_TTL_SECONDS = 60.0
_MIN_SPACING_SECONDS = 2.0
_RETRY_AFTER_THROTTLE_SECONDS = 3.0
_cache: dict[str, tuple[float, "PriceQuote"]] = {}
_cache_lock = _threading.Lock()
_last_request_ts = [0.0]


def _cache_get(key: str):
    with _cache_lock:
        v = _cache.get(key)
        if v is None:
            return None
        ts, quote = v
        if _time.monotonic() - ts > _CACHE_TTL_SECONDS:
            del _cache[key]
            return None
        return quote


def _cache_put(key: str, quote: "PriceQuote") -> None:
    with _cache_lock:
        _cache[key] = (_time.monotonic(), quote)


async def _throttle() -> None:
    """Sleep until at least _MIN_SPACING_SECONDS have passed since the last request."""
    while True:
        now = _time.monotonic()
        wait = _MIN_SPACING_SECONDS - (now - _last_request_ts[0])
        if wait <= 0:
            _last_request_ts[0] = now
            return
        await _asyncio.sleep(wait)


class ProviderError(RuntimeError):
    pass


@dataclass
class PriceQuote:
    price: float
    source: str
    timestamp: datetime
    raw_symbol: str = ""
    currency: str = "CNY"
    name: str = ""

    def to_dict(self) -> dict:
        return {
            "price": self.price,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "raw_symbol": self.raw_symbol,
            "currency": self.currency,
            "name": self.name,
        }


class PriceProvider(ABC):
    name: str = "base"
    currency: str = "CNY"

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> PriceQuote:
        ...


# --------------------------------------------------------------------------- #
# Tencent Finance — unified provider for A-shares, ETFs, indexes, HK, US
# --------------------------------------------------------------------------- #

class TencentFinanceProvider(PriceProvider):
    """Market-specific Tencent Finance quotes."""

    # Each subclass declares the URL prefix and the currency for the market
    url_prefix: str = ""           # e.g. "sh", "sz", "hk", "us"
    currency: str = "CNY"
    requires_period: bool = False   # Some US tickers need ".OQ" / ".N" suffix

    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> PriceQuote:
        sym = symbol.strip().lower()
        cache_key = f"{self.url_prefix}:{sym}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        await _throttle()
        url = f"https://qt.gtimg.cn/q={self.url_prefix}{sym}"
        last_err: Exception | None = None
        text = ""
        r = None
        for attempt in range(2):
            try:
                r = await client.get(url, headers=_BROWSER_HEADERS, timeout=8.0)
                r.raise_for_status()
                text = r.content.decode("gbk", errors="replace")
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt == 0:
                    await asyncio.sleep(0.5)
        if last_err is not None:
            raise ProviderError(f"Tencent request failed: {last_err}") from last_err

        # Expected: v_<prefix><sym>="..." or v_pv_none_match="1"
        if "pv_none_match" in text:
            # Throttled — wait a beat and try one more time before giving up
            await asyncio.sleep(_RETRY_AFTER_THROTTLE_SECONDS)
            try:
                r = await client.get(url, headers=_BROWSER_HEADERS, timeout=8.0)
                r.raise_for_status()
                text = r.content.decode("gbk", errors="replace")
            except Exception as e:
                raise ProviderError(
                    f"Tencent: no data for {self.url_prefix}{symbol}: {e}"
                ) from e
            if "pv_none_match" in text:
                raise ProviderError(
                    f"Tencent: no data for {self.url_prefix}{symbol} (possibly throttled — wait a minute and try again)"
                )
        m = re.search(r'"(.*)"', text)
        if not m:
            raise ProviderError(f"Tencent: missing quotes in payload for {self.url_prefix}{symbol}")
        if not m or not m.group(1):
            raise ProviderError(f"Tencent: empty payload for {self.url_prefix}{symbol}")
        parts = m.group(1).split("~")
        if len(parts) <= 3 or not parts[3].strip():
            raise ProviderError(f"Tencent: payload too short: {parts}")
        try:
            price = float(parts[3])
        except Exception as e:
            raise ProviderError(f"Tencent: price parse failed: {parts[3]!r}") from e
        if price <= 0:
            raise ProviderError(f"Tencent: non-positive price {price}")
        quote = PriceQuote(
            price=price,
            source="tencent",
            timestamp=datetime.now(timezone.utc),
            raw_symbol=f"{self.url_prefix}{sym}",
            currency=self.currency,
            name=parts[1].strip() if len(parts) > 1 else "",
        )
        _cache_put(cache_key, quote)
        return quote


class TencentSHProvider(TencentFinanceProvider):
    url_prefix = "sh"
    name = "tencent_sh"
    currency = "CNY"


class TencentSZProvider(TencentFinanceProvider):
    url_prefix = "sz"
    name = "tencent_sz"
    currency = "CNY"


class TencentHKProvider(TencentFinanceProvider):
    url_prefix = "hk"
    name = "tencent_hk"
    currency = "HKD"


class TencentFundProvider(TencentFinanceProvider):
    """Open-end fund daily NAV via fundgz (real-time estimate fallback)."""

    url_prefix = ""
    name = "tencent_fund"
    currency = "CNY"

    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> PriceQuote:
        url = f"https://fundgz.1234567.com.cn/js/{symbol}.js"
        try:
            r = await client.get(url, headers=_BROWSER_HEADERS, timeout=8.0)
            r.raise_for_status()
            text = r.text
        except Exception as e:
            text = ""
        if "jsonpgz" in text:
            import json
            m = re.search(r"jsonpgz\((.*)\);?", text)
            if not m:
                raise ProviderError(f"Fundgz: unexpected response: {text[:120]}")
            try:
                data = json.loads(m.group(1))
            except Exception as e:
                raise ProviderError(f"Fundgz: JSON parse failed: {e}") from e
            price_str = data.get("dwjz") or data.get("gsz")
            if not price_str:
                raise ProviderError("Fundgz: missing dwjz/gsz field")
            return PriceQuote(
                price=float(price_str),
                source="fundgz",
                timestamp=datetime.now(timezone.utc),
                raw_symbol=symbol,
                currency=self.currency,
                name=str(data.get("name") or ""),
            )
        # fundgz has no estimate coverage for some funds (QDII / non-estimate) —
        # fall back to Eastmoney pingzhongdata: fS_name + latest unit NAV
        return await self._fetch_pingzhongdata(client, symbol)

    async def _fetch_pingzhongdata(self, client: httpx.AsyncClient, symbol: str) -> PriceQuote:
        url = f"https://fund.eastmoney.com/pingzhongdata/{symbol}.js"
        try:
            r = await client.get(url, headers=_BROWSER_HEADERS, timeout=15.0)
            r.raise_for_status()
            text = r.text
        except Exception as e:
            raise ProviderError(f"Fund quote unavailable for {symbol}: {e}") from e
        m_name = re.search(r'fS_name = "(.*?)"', text)
        # Money-market funds have no unit NAV series (nav is pinned at 1.0);
        # pingzhongdata flags them with ishb=true and carries the per-10k
        # income series instead — quote them at par so refresh works.
        m_ishb = re.search(r'ishb\s*=\s*"?([^";]*)', text)
        if m_ishb and m_ishb.group(1) == "true":
            return PriceQuote(
                price=1.0,
                source="eastmoney-money-market",
                timestamp=datetime.now(timezone.utc),
                raw_symbol=symbol,
                currency=self.currency,
                name=m_name.group(1) if m_name else "",
            )
        # unit NAV series only (not the accumulated-NAV series that follows it);
        # string slicing instead of a DOTALL regex — the 700KB payload would
        # cause catastrophic backtracking and block the event loop
        last_nav = None
        idx = text.find("Data_netWorthTrend")
        if idx != -1:
            end = text.find("];", idx)
            seg = text[idx:end]
            ys = re.findall(r'"y":([0-9.]+)', seg)
            if ys:
                last_nav = float(ys[-1])
        if last_nav is None or last_nav <= 0:
            raise ProviderError(f"Eastmoney: no NAV data for {symbol}")
        return PriceQuote(
            price=last_nav,
            source="eastmoney",
            timestamp=datetime.now(timezone.utc),
            raw_symbol=symbol,
            currency=self.currency,
            name=m_name.group(1) if m_name else "",
        )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def get_provider(exchange: str) -> Optional[PriceProvider]:
    ex = (exchange or "").upper()
    if ex == "SH":
        return TencentSHProvider()
    if ex == "SZ":
        return TencentSZProvider()
    if ex == "HK":
        return TencentHKProvider()
    if ex == "FUND_CN":
        return TencentFundProvider()
    return None


def list_supported_exchanges() -> list[str]:
    return ["SH", "SZ", "FUND_CN", "HK"]


def list_manual_only_exchanges() -> list[str]:
    """Exchanges that work but require manual price entry due to upstream throttling."""
    return ["US", "CRYPTO"]


async def fetch_price(
    symbol: str,
    exchange: str,
    ifind_username: Optional[str] = None,
    ifind_password: Optional[str] = None,
) -> PriceQuote:
    """Single-call convenience wrapper.

    When iFinD credentials are supplied AND the iFinDPy package is available,
    iFinD is tried first (it is the authoritative source for A-shares / ETFs /
    HK / open-end funds). On any iFinD failure we degrade gracefully to the
    Tencent provider so the user is never blocked by an iFinD outage.
    """
    if ifind_username and ifind_password:
        try:
            from . import ifind_client
            if ifind_client.is_available() and ifind_client.supports_exchange(exchange):
                q = await ifind_client.fetch_realtime(ifind_username, ifind_password, symbol, exchange)
                return PriceQuote(
                    price=q["price"],
                    source=q["source"],
                    timestamp=datetime.now(timezone.utc),
                    raw_symbol=q["thscode"],
                    currency=q["currency"],
                    name=q.get("name") or "",
                )
        except Exception as e:
            # Degrade to Tencent rather than surfacing the iFinD error — but
            # record the reason so callers can surface it if Tencent also fails.
            _last_ifind_error[0] = str(e)
        else:
            _last_ifind_error[0] = ""

    provider = get_provider(exchange)
    if provider is None:
        raise ProviderError(
            f"No provider for exchange={exchange!r}. Supported: {list_supported_exchanges()}"
        )
    async with httpx.AsyncClient() as client:
        return await provider.fetch(client, symbol)


# Stores the most recent iFinD failure reason (for diagnostics when we degrade)
_last_ifind_error: list[str] = [""]


def last_ifind_error() -> str:
    return _last_ifind_error[0]


async def fetch_fund_meta(symbol: str) -> Optional[tuple[str, bool]]:
    """(name, is_money_market) from eastmoney pingzhongdata; None if unreachable.

    Needed because the iFinD realtime branch of fetch_price returns no name —
    pingzhongdata's fS_name / ishb headers fill that gap for CN funds.
    """
    url = f"https://fund.eastmoney.com/pingzhongdata/{symbol}.js"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=_BROWSER_HEADERS, timeout=15.0)
            r.raise_for_status()
            text = r.text
        m_name = re.search(r'fS_name = "(.*?)"', text)
        m_ishb = re.search(r'ishb\s*=\s*"?([^";]*)', text)
        if not m_name:
            return None
        return m_name.group(1), m_ishb is not None and m_ishb.group(1) == "true"
    except Exception:
        return None