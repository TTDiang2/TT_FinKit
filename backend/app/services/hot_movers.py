"""热点页数据服务 — 两个视窗（用户拍板 2026-08-29）：

  持仓层：用户当前持仓，价格每日自动更新后即可看当日/近5日/近21日异动；
  全池层：全部入池标的，基于预计算表 research_asset_stats（数据截至
          最近一次全量更新，明确标注 last_date）。

榜单全部读预计算表/轻量查询，不做全表扫描。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.investment import Investment, open_position_cond
from ..models.research_asset import ResearchAsset, ResearchAssetPrice
from ..models.research_asset_stats import ResearchAssetStats


async def hot_overview(pub: AsyncSession, user_id: str, priv: AsyncSession | None = None) -> dict:
    today = date.today().isoformat()

    # ---- 全池层（读预计算表，零重算）----
    stats = (await pub.execute(
        select(ResearchAssetStats).where(ResearchAssetStats.status == "pooled")
    )).scalars().all()
    valid = [s for s in stats if s.last_date]
    data_as_of = max((s.last_date for s in valid), default=None)

    def top(field: str, n: int = 10, exclude_newer: str | None = None):
        rows = [s for s in valid
                if getattr(s, field) is not None
                and (exclude_newer is None or (s.last_date or "") >= exclude_newer)]
        rows.sort(key=lambda s: (getattr(s, field) or 0), reverse=True)
        return [{"symbol": s.symbol, "name": s.name,
                 "value": getattr(s, field), "last_date": s.last_date}
                for s in rows[:n]]

    fresh_cut = (date.today() - timedelta(days=35)).isoformat()
    hot_pool = {
        "data_as_of": data_as_of,
        "movers_21d": top("ret_21d", 10),
        "movers_63d": top("ret_63d", 10),
        "movers_252d": top("ret_252d", 10),
        "sharpe_1y": top("sharpe_1y", 10),
        "new_strong": [
            {"symbol": s.symbol, "name": s.name, "value": s.ret_252d,
             "last_date": s.last_date}
            for s in valid
            # 新入池强势：近 35 天开始有数据且 1 年收益为正
            if s.rows is not None and s.rows < 260
            and (s.ret_252d or -9) > 0.2
        ][:10],
        "stale_note": None if (data_as_of and data_as_of >= fresh_cut) else
        f"全池数据截至 {data_as_of}（超过 35 天未全量更新，建议先做全量数据更新再看全市场异动）",
    }

    # ---- 持仓层（当日价格已自动更新，实时异动）----
    # Investment 在 private 库：优先用 priv，单库模式回退 pub（同一 session）
    inv_sess = priv or pub
    invs = (await inv_sess.execute(
        select(Investment).where(Investment.user_id == user_id, open_position_cond())
    )).scalars().all()
    held_syms = [i.symbol for i in invs if i.symbol]
    holdings: list[dict] = []
    if held_syms:
        rows = (await pub.execute(
            select(ResearchAsset.symbol, ResearchAsset.name,
                   ResearchAssetPrice.date, ResearchAssetPrice.close)
            .join(ResearchAsset, ResearchAsset.id == ResearchAssetPrice.asset_id)
            .where(ResearchAsset.symbol.in_(held_syms),
                   ResearchAssetPrice.date >= (date.today() - timedelta(days=45)).isoformat())
            .order_by(ResearchAsset.symbol, ResearchAssetPrice.date)
        )).all()
        series: dict[str, list[tuple[str, float]]] = {}
        names: dict[str, str] = {}
        for sym, name, d, close in rows:
            series.setdefault(sym, []).append((d, float(close)))
            names[sym] = name
        for sym in held_syms:
            ser = series.get(sym) or []
            if len(ser) < 2:
                continue
            closes = [c for _, c in ser]

            def wret(n: int) -> float | None:
                if len(closes) <= n or closes[-n - 1] <= 0:
                    return None
                return closes[-1] / closes[-n - 1] - 1.0

            holdings.append({
                "symbol": sym, "name": names.get(sym, sym),
                "last_date": ser[-1][0],
                "ret_1d": wret(1), "ret_5d": wret(5), "ret_21d": wret(21),
            })
    holdings.sort(key=lambda x: (x.get("ret_1d") or 0), reverse=True)

    return {
        "as_of": today,
        "pool": hot_pool,
        "holdings": {"data_as_of": max((h["last_date"] for h in holdings), default=None),
                     "items": holdings},
    }


async def refresh_holdings_prices(db: AsyncSession, user_id: str,
                                  pub: AsyncSession | None = None,
                                  max_funds: int = 50) -> int:
    """当前持仓标的的价格补拉（东财 pingzhongdata 单请求全历史，限速）。

    供启动钩子调用：持仓就几只，1.5s/只 ≈ 秒级完成。

    跨库：`Investment` 在 private，`ResearchAsset`/`ResearchAssetPrice` 在 public。
    单库模式下 pub=None 即退化为同一个 session，行为不变。
    """
    import asyncio
    from . import fund_profile  # noqa: F401  (确保 akshare 环境已初始化)
    from .nav_history import fetch_history_series
    from ..models.research_asset import ResearchAsset
    from ..models.investment import Investment, open_position_cond
    from ..models.research_asset import ResearchAssetPrice

    pdb = pub if pub is not None else db

    # Investment 在 private 库 → 用 db（private 会话）；研究价格表在 public → 用 pdb
    invs = (await db.execute(
        select(Investment).where(Investment.user_id == user_id, open_position_cond())
    )).scalars().all()
    syms = [i.symbol for i in invs if i.symbol][:max_funds]
    if not syms:
        return 0
    assets = (await pdb.execute(
        select(ResearchAsset).where(ResearchAsset.user_id == user_id,
                                    ResearchAsset.symbol.in_(syms))
    )).scalars().all()
    updated = 0
    for a in assets:
        try:
            last = (await pdb.execute(
                select(ResearchAssetPrice.date).where(ResearchAssetPrice.asset_id == a.id)
                .order_by(ResearchAssetPrice.date.desc()).limit(1)
            )).scalar()
            begin = "2021-08-01"  # 单请求全历史，日期窗口不影响请求次数
            series, _src = await fetch_history_series(a.symbol, a.exchange or "FUND_CN",
                                                      begin, date.today().isoformat())
            n_new = 0
            for row in series:
                d, px = row["date"], float(row["close"])
                exists = (await pdb.execute(
                    select(ResearchAssetPrice.id).where(
                        ResearchAssetPrice.asset_id == a.id,
                        ResearchAssetPrice.date == d)
                )).scalar_one_or_none()
                if not exists:
                    pdb.add(ResearchAssetPrice(asset_id=a.id, date=d, close=px,
                                               source="holdings-daily"))
                    n_new += 1
            await pdb.commit()
            updated += 1
            if n_new:
                await asyncio.sleep(1.2)  # 限速
        except Exception:  # noqa: BLE001 — 单只失败不阻断
            continue
    return updated
