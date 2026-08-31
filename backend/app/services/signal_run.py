"""每日自动信号 — 应用启动时若当日未跑过信号且有持仓则后台补跑。

用户拍板（2026-08-29）：打开应用自动跑当日信号（数据依赖当日价格，
拉数脚本/手动更新完成后信号才反映最新净值，故放在 startup 延迟执行）。
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.signal import Signal
from ..models.strategy import Strategy


async def _active_strategy_user(pub: AsyncSession) -> tuple[Strategy | None, str | None]:
    """策略无 user_id（全局激活）——属主从入池标的推断。"""
    from ..models.research_asset import ResearchAsset
    strat = (await pub.execute(
        select(Strategy).where(Strategy.activated_at.isnot(None))
        .order_by(Strategy.activated_at.desc()).limit(1)
    )).scalar_one_or_none()
    if not strat:
        return None, None
    uid = (await pub.execute(
        select(ResearchAsset.user_id).where(ResearchAsset.status == "pooled").limit(1)
    )).scalar()
    return strat, uid


async def run_signal_for_user(db: AsyncSession, pub: AsyncSession, user_id: str) -> dict:
    """与 POST /api/signals/run 相同的逻辑（供启动钩子复用）。"""
    from .signal_service import get_active_strategy, save_signal
    from .signal_engine import generate_signal
    from ..models.research_asset import ResearchAsset

    strat = await get_active_strategy(pub)
    if not strat:
        return {"status": "error", "error": "no active strategy"}

    universe_q = select(ResearchAsset).where(ResearchAsset.status == "pooled")
    if strat.group_id:
        from app.models.research_group import ResearchGroupMember
        member_ids = select(ResearchGroupMember.asset_id).where(
            ResearchGroupMember.group_id == strat.group_id)
        universe_q = universe_q.where(ResearchAsset.id.in_(member_ids))
    assets = list((await pub.execute(universe_q)).scalars().all())
    universe = [a.symbol for a in assets]
    if not universe:
        return {"status": "error", "error": "universe empty"}

    from ..routers.signals import _current_weights_from_holdings
    current_weights = await _current_weights_from_holdings(db, pub, user_id)

    from ..config import _resolve_public_url
    result = generate_signal(
        strategy_code=strat.code, params={}, universe=universe,
        rebalance_freq=strat.rebalance_freq or "monthly",
        current_weights=current_weights,
        db_path=_resolve_public_url().split("///")[-1],
    )
    if result["status"] != "ok":
        return {"status": "error", "error": result.get("error")}
    sig = await save_signal(
        db, strategy_id=strat.id, strategy_version=strat.version,
        run_date=date.today().isoformat(), as_of_date=result["as_of_date"],
        next_rebalance_date=result["next_rebalance_date"],
        target_weights=result["target_weights"],
        risk_status=result["risk_status"],
    )
    return {"status": "ok", "signal_id": sig.id}


async def maybe_run_daily_signal(max_wait_s: int = 90) -> dict:
    """启动钩子入口：延迟执行，避免阻塞应用启动；幂等（当日已有信号则跳过）。

    全程分三个短会话阶段——启动任务与 HTTP 请求共享连接池，长会话横跨
    多个请求周期会触发 IllegalStateChangeError 竞态（2026-08-30 事故）。
    """
    import asyncio
    await asyncio.sleep(min(30, max_wait_s))  # 等价格更新/DB 就绪
    from ..database import async_session_maker

    # 阶段 1：检查是否需要跑
    async with async_session_maker() as db:
        strat, user_id = await _active_strategy_user(db)
        if not strat or not user_id:
            return {"status": "skipped", "reason": "no active strategy"}
        today = date.today().isoformat()
        latest = (await db.execute(
            select(Signal).order_by(Signal.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if latest and latest.run_date == today:
            return {"status": "skipped", "reason": "already ran today"}
        from ..models.investment import Investment, open_position_cond
        n_pos = len((await db.execute(
            select(Investment).where(Investment.user_id == user_id, open_position_cond())
        )).scalars().all())
        if n_pos == 0:
            return {"status": "skipped", "reason": "no open positions"}

    # 阶段 2：持仓层数据每日自动拉（独立短会话）
    try:
        async with async_session_maker() as db2:
            from .hot_movers import refresh_holdings_prices
            await refresh_holdings_prices(db2, user_id)
    except Exception:  # noqa: BLE001 — 数据层失败不影响信号
        pass

    # 阶段 3：跑信号（独立短会话）
    async with async_session_maker() as db3, public_session_maker() as pub3:
        return await run_signal_for_user(db3, pub3, user_id)
