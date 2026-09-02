"""Research asset price warehouse: full/incremental sync + indicator computation.

Prices are pulled through ``nav_history.fetch_history_series`` (iFinD →
eastmoney → tencent → akshare, cached) and persisted into ``research_prices``.
Indicators reuse ``services/indicators`` so pool numbers match the holdings
detail page exactly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..schemas.research_asset import ResearchAssetIndicators, SyncResult
from . import nav_history
from .indicators import (
    annualized_return,
    annualized_volatility,
    max_drawdown,
    sharpe_ratio,
)

_FULL_BEGIN = "1990-01-01"

# SQLite caps bind parameters per statement (32766 on modern builds); bulk
# inserts must be chunked or a 5000-row history blows the limit
_BATCH = 500


def _price_rows(asset_id: str, series: list[dict], source: str) -> list[dict]:
    return [
        {
            "asset_id": asset_id,
            "date": p["date"],
            "nav": None,
            "acc_nav": None,
            "close": float(p["close"]),
            "source": source,
        }
        for p in series
    ]


def _chunks(rows: list[dict]) -> list[list[dict]]:
    return [rows[i : i + _BATCH] for i in range(0, len(rows), _BATCH)]


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


async def sync_asset_prices(
    db: AsyncSession,
    asset: ResearchAsset,
    ifind_user: Optional[str] = None,
    ifind_pass: Optional[str] = None,
    full: bool = False,
) -> SyncResult:
    """Pull prices for one asset and persist them (idempotent upsert).

    full=True wipes and re-imports the whole history; otherwise only the tail
    from the latest stored date (re-pulled, so corrections land) is fetched.
    """
    latest = (
        await db.execute(
            select(ResearchAssetPrice.date)
            .where(ResearchAssetPrice.asset_id == asset.id)
            .order_by(ResearchAssetPrice.date.desc())
            .limit(1)
        )
    ).scalar()

    if full or latest is None:
        begin = _FULL_BEGIN
        await db.execute(delete(ResearchAssetPrice).where(ResearchAssetPrice.asset_id == asset.id))
    else:
        begin = latest  # re-pull the last day: source corrections overwrite it
    end = _today_str()

    try:
        series, source = await nav_history.fetch_history_series(
            asset.symbol,
            asset.exchange or "FUND_CN",
            begin,
            end,
            ifind_user,
            ifind_pass,
            force_money_market=bool(asset.is_money_market),
        )
    except nav_history.NavHistoryError as e:
        return SyncResult(asset_id=asset.id, error=str(e))

    if series:
        rows = _price_rows(asset.id, series, source)
        if full or latest is None:
            for chunk in _chunks(rows):
                await db.execute(sqlite_insert(ResearchAssetPrice).values(chunk))
        else:
            for chunk in _chunks(rows):
                await db.execute(
                    sqlite_insert(ResearchAssetPrice)
                    .values(chunk)
                    .on_conflict_do_update(
                        index_elements=["asset_id", "date"],
                        set_={
                            "close": sqlite_insert(ResearchAssetPrice).excluded.close,
                            "source": source,
                        },
                    )
                )
        await db.commit()

    return SyncResult(
        asset_id=asset.id,
        rows=len(series),
        source=source,
        begin=series[0]["date"] if series else "",
        end=series[-1]["date"] if series else "",
    )


def compute_asset_indicators(
    asset: ResearchAsset,
    prices: list[ResearchAssetPrice],
) -> ResearchAssetIndicators:
    """Pool indicators from the stored close series (ascending by date).

    Money-market funds: vol/sharpe/ann_return are None (near-constant series
    would explode the ratios — same rule as the closed-positions table).

    Two Sharpe windows are returned:
    - Full-sample: geometric annualized return / vol over the whole series
    - Trailing 1Y: same ratios over the last 252 trading days, matching ret_1y
    """
    prices = sorted(prices, key=lambda p: p.date)
    closes = [p.close for p in prices]
    if not closes:
        return ResearchAssetIndicators()

    today = date.today()
    dates = [date.fromisoformat(p.date) for p in prices]

    def _ret_over(days: int) -> Optional[float]:
        cutoff = today - timedelta(days=days)
        idx = None
        for i, d in enumerate(dates):
            if d <= cutoff:
                idx = i
            else:
                break
        if idx is None:
            # 序列够不到窗口起点：总跨度不足窗口的 2/3 视为数据不足
            # （如 19 天历史不该产出"1 个月收益"）
            if (dates[-1] - dates[0]).days < days * 2 // 3:
                return None
            idx = 0
        if idx >= len(closes) - 1:
            return None
        base = closes[idx]
        return closes[-1] / base - 1.0 if base > 0 else None

    if asset.is_money_market:
        return ResearchAssetIndicators(
            points=len(closes),
            first_date=prices[0].date,
            last_date=prices[-1].date,
            latest_close=closes[-1],
        )

    full_ann_return = annualized_return(closes)
    full_ann_vol = annualized_volatility(closes)
    full_sharpe = sharpe_ratio(closes)

    trailing_closes = closes[-252:]
    trailing_ann_return = annualized_return(trailing_closes) if len(trailing_closes) >= 2 else None
    trailing_ann_vol = annualized_volatility(trailing_closes) if len(trailing_closes) >= 2 else None
    trailing_sharpe = sharpe_ratio(trailing_closes) if (trailing_ann_return is not None and trailing_ann_vol is not None) else None

    return ResearchAssetIndicators(
        points=len(closes),
        first_date=prices[0].date,
        last_date=prices[-1].date,
        latest_close=closes[-1],
        ret_1m=_ret_over(30),
        ret_1y=_ret_over(365),
        ann_return=full_ann_return,
        ann_volatility=full_ann_vol,
        sharpe=full_sharpe,
        ann_return_1y=trailing_ann_return,
        ann_volatility_1y=trailing_ann_vol,
        sharpe_1y=trailing_sharpe,
        max_drawdown=max_drawdown(closes),
    )


async def load_indicators(db: AsyncSession, asset: ResearchAsset) -> ResearchAssetIndicators:
    prices = (
        await db.execute(
            select(ResearchAssetPrice)
            .where(ResearchAssetPrice.asset_id == asset.id)
            .order_by(ResearchAssetPrice.date)
        )
    ).scalars().all()
    return compute_asset_indicators(asset, list(prices))


async def refresh_all_pooled(
    db: AsyncSession,
    user_id: str,
    ifind_user: Optional[str] = None,
    ifind_pass: Optional[str] = None,
) -> list[SyncResult]:
    """Incremental refresh for every pooled asset, serial and failure-isolated."""
    assets = (
        await db.execute(
            select(ResearchAsset).where(
                ResearchAsset.user_id == user_id, ResearchAsset.status == "pooled"
            ).order_by(ResearchAsset.created_at)
        )
    ).scalars().all()

    results: list[SyncResult] = []
    for asset in assets:
        try:
            results.append(await sync_asset_prices(db, asset, ifind_user, ifind_pass))
        except Exception as e:  # noqa: BLE001 — one bad source must not kill the batch
            results.append(SyncResult(asset_id=asset.id, error=str(e)))
    return results


def lag_days(last_date: Optional[str]) -> Optional[int]:
    if not last_date:
        return None
    try:
        return (date.today() - date.fromisoformat(last_date)).days
    except ValueError:
        return None
