"""实盘策略健康监控 — 监控页「策略失效判定 / 调仓冷却 / 数据新鲜度」的后端。

用户拍板（2026-08-29）：
  失效告警阈值 = 回撤 > 1.25×回测最大回撤 或 滚动126日年化 < 回测年化一半 → 黄；
  黄色状态持续 63 个交易日 → 红（持续未修复）。
  调仓记录 = 手动按钮 + 投资流水自动检测（互为兜底）。
  数据更新 = 月度全量提醒（last_date 距今 > 25 天时提醒全量更新）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.backtest import Backtest
from ..models.investment import Investment, open_position_cond
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..models.signal import Signal
from ..models.strategy import Strategy

YELLOW_MDD_MULT = 1.25
YELLOW_ROLL_ANN_FRAC = 0.5
ROLL_WINDOW = 126
RED_PERSIST_DAYS = 63
FRESH_REMIND_DAYS = 25


async def _active_strategy(db: AsyncSession) -> Strategy | None:
    return (await db.execute(
        select(Strategy).where(Strategy.activated_at.isnot(None))
        .order_by(Strategy.activated_at.desc()).limit(1)
    )).scalar_one_or_none()


async def _canonical_backtest(db: AsyncSession, strategy_id: str) -> Backtest | None:
    """健康基准 = 该策略「窗口最长」的完成回测（正式验证跑），而非最近一次
    ——短窗口试验/组合测试会污染基线。"""
    rows = (await db.execute(
        select(Backtest).where(Backtest.strategy_id == strategy_id, Backtest.status == "done")
    )).scalars().all()
    if not rows:
        return None
    def span(b: Backtest) -> int:
        try:
            return (date.fromisoformat(str(b.end_date)[:10])
                    - date.fromisoformat(str(b.start_date)[:10])).days
        except (ValueError, TypeError):
            return 0
    return max(rows, key=span)


async def _last_rebalance_date(db: AsyncSession, user_id: str) -> tuple[str | None, str]:
    """最近一次调仓：手动记录 vs 投资流水自动检测，取较新者。

    投资流水全在 private 库（investments 本就是用户自己的持仓），
    双库拆分后原 research_assets 过滤已无意义（认领后用户持有全部入池标的）。
    """
    from ..models.user_settings import UserSettings
    row = (await db.execute(select(UserSettings).where(
        UserSettings.user_id == user_id))).scalar_one_or_none()
    data: dict = {}
    if row and row.monitor_thresholds:
        try:
            data = json.loads(row.monitor_thresholds)
        except (ValueError, TypeError):
            data = {}
    manual = data.get("last_manual_rebalance")
    # 流水自动检测：持仓标的上的买/卖流水（近 90 天足够）
    auto_row = (await db.execute(text(
        """
        SELECT MAX(substr(it.event_date, 1, 10))
        FROM investment_transactions it
        JOIN investments i ON i.id = it.investment_id
        WHERE i.user_id = :u
          AND it.event_type IN ('buy', 'sell', 'purchase', 'redeem', 'subscribe')
        """
    ), {"u": user_id})).scalar()
    candidates = [x for x in (manual, auto_row) if x]
    if not candidates:
        return None, "无记录"
    latest = max(candidates)
    src = "手动确认" if (manual and manual == latest) else "流水检测"
    return latest, src


async def strategy_health(db: AsyncSession, pub: AsyncSession, user_id: str) -> dict:
    """监控页核心负载：策略健康 + 调仓冷却 + 数据新鲜度。

    db = private（回测/信号/持仓/设置），pub = public（策略/标的/价格）。
    """
    today = date.today()
    out: dict = {"as_of": today.isoformat()}

    strat = await _active_strategy(pub)
    out["strategy"] = {"id": strat.id, "name": strat.name, "version": strat.version} if strat else None

    # ---- 基准：最近一次完成回测的指标 + 失效扫描 ----
    base_metrics, stagnant = None, []
    if strat:
        bt = await _canonical_backtest(db, strat.id)
        if bt and bt.results:
            res = json.loads(bt.results)
            base_metrics = res.get("metrics")
            stagnant = (res.get("stagnant_analysis") or {}).get("merged_periods") or []
            out["backtest"] = {"id": bt.id, "start": bt.start_date, "end": bt.end_date,
                               "ann": (base_metrics or {}).get("ann_return"),
                               "sharpe": (base_metrics or {}).get("sharpe"),
                               "mdd": (base_metrics or {}).get("max_drawdown")}
    out["stagnant_periods"] = stagnant

    # ---- 最新信号 + 实盘漂移（信号日至今的组合收益/回撤）----
    sig = (await db.execute(select(Signal).order_by(Signal.created_at.desc()).limit(1)
                            )).scalar_one_or_none()
    out["signal"] = {"run_date": sig.run_date if sig else None,
                     "next_rebalance": sig.next_rebalance_date if sig else None} if sig else None
    drift = {"since": None, "ret": None, "mdd": None, "level": "no_data"}
    if sig and sig.target_weights:
        tw = json.loads(sig.target_weights or "{}")
        held = [s for s, w in tw.items() if w and w > 1e-6]
        if held and sig.run_date:
            since = max(sig.run_date, (today - timedelta(days=ROLL_WINDOW + 30)).isoformat())
            rows = (await pub.execute(
                select(ResearchAsset.symbol, ResearchAssetPrice.date, ResearchAssetPrice.close)
                .join(ResearchAsset, ResearchAsset.id == ResearchAssetPrice.asset_id)
                .where(ResearchAsset.symbol.in_(held),
                       ResearchAssetPrice.date >= since)
                .order_by(ResearchAssetPrice.date)
            )).all()
            by_sym: dict[str, list[tuple[str, float]]] = {}
            for sym, d, close in rows:
                by_sym.setdefault(sym, []).append((d, float(close)))
            if by_sym:
                dates = sorted({d for ser in by_sym.values() for d, _ in ser})
                dates = dates[-ROLL_WINDOW - 1:]
                nav_series: list[float] = []
                for d in dates:
                    nav = 0.0
                    wsum = 0.0
                    for sym in held:
                        ser = dict(by_sym.get(sym) or [])
                        if d in ser:
                            nav += tw[sym] * ser[d]
                            wsum += tw[sym]
                    if wsum > 0:
                        nav_series.append(nav / wsum)
                if len(nav_series) >= 20:
                    ret = nav_series[-1] / nav_series[0] - 1.0
                    peak, mdd = nav_series[0], 0.0
                    for v in nav_series:
                        peak = max(peak, v)
                        if peak > 0:
                            mdd = min(mdd, v / peak - 1.0)
                    drift = {"since": dates[0], "ret": ret, "mdd": mdd, "level": "ok"}
    out["live_drift"] = drift

    # ---- 失效判定（用户拍板的默认阈值）----
    # 实盘未开始（无调仓记录）时不做红判：回测失效扫描的历史停滞段
    # 不代表实盘失效（2026-09-02 用户反馈刚激活就被判「失效」）
    last_rb, rb_src = await _last_rebalance_date(db, user_id)
    level, reasons = "ok", []
    if not last_rb:
        reasons.append("实盘尚未开始执行调仓，失效判定将在首笔调仓后启用")
    if base_metrics and drift["mdd"] is not None:
        bt_mdd = base_metrics.get("max_drawdown") or 0.0
        bt_ann = base_metrics.get("ann_return") or 0.0
        if bt_mdd < 0 and drift["mdd"] < bt_mdd * YELLOW_MDD_MULT:
            reasons.append(f"实盘回撤 {drift['mdd']*100:.1f}% 已超过回测回撤"
                           f" {bt_mdd*100:.1f}% 的 {YELLOW_MDD_MULT:.2f} 倍")
        # 滚动年化：信号日以来不足 126 日时跳过（样本太短）
        if drift["since"] and drift["ret"] is not None:
            days = (today - date.fromisoformat(drift["since"])).days
            if days >= ROLL_WINDOW and bt_ann > 0:
                roll_ann = (1.0 + drift["ret"]) ** (252.0 / max(1, ROLL_WINDOW)) - 1.0
                if roll_ann < bt_ann * YELLOW_ROLL_ANN_FRAC:
                    reasons.append(f"滚动{ROLL_WINDOW}日年化 {roll_ann*100:.1f}% 低于"
                                   f" 回测年化 {bt_ann*100:.1f}% 的一半")
    if reasons:
        level = "yellow"
        # 持续性 → 红：失效扫描里存在覆盖最近 63 日的失效段
        if stagnant and last_rb:
            for p in stagnant:
                if p.get("end", "0000") >= (today - timedelta(days=RED_PERSIST_DAYS)).isoformat():
                    level = "red"
                    reasons.append("失效区间持续超过 63 个交易日（回测失效扫描）")
                    break
    out["health"] = {"level": level, "reasons": reasons,
                     "rules": {"yellow_mdd_mult": YELLOW_MDD_MULT,
                               "yellow_roll_ann_frac": YELLOW_ROLL_ANN_FRAC,
                               "roll_window": ROLL_WINDOW,
                               "red_persist_days": RED_PERSIST_DAYS}}

    # ---- 调仓冷却 ----
    cooldown_until = None
    if last_rb:
        d0 = date.fromisoformat(str(last_rb)[:10])
        cooldown_until = (d0 + timedelta(days=14)).isoformat()
    out["rebalance"] = {"last_date": last_rb, "source": rb_src,
                        "cooldown_until": cooldown_until,
                        "in_cooldown": bool(cooldown_until and today.isoformat() <= cooldown_until)}

    # ---- 数据新鲜度（月度全量更新提醒）----
    max_row = (await pub.execute(text(
        "SELECT MAX(rp.date) FROM research_prices rp "
        "JOIN research_assets ra ON ra.id = rp.asset_id WHERE ra.status='pooled'"
    ))).scalar()
    lag = None
    if max_row:
        lag = (today - date.fromisoformat(str(max_row)[:10])).days
    out["data_freshness"] = {"max_date": max_row, "lag_days": lag,
                             "remind_full_update": bool(lag is not None and lag > FRESH_REMIND_DAYS),
                             "remind_after_days": FRESH_REMIND_DAYS}
    return out
