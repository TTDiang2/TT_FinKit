"""AI 咨询 — 真实财务数据聚合。

把记账（收入/支出/转账）、账户余额、投资持仓聚合成一份结构化快照，
作为 AI（严厉财富审计师人设）的事实依据。所有数字都来自真实表，
AI 只被允许引用这份快照里的数字。
"""
from __future__ import annotations

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .emergency_reserve import compute_emergency_reserve
from .housing_plan import build_housing_snapshot, get_housing_plan
from .investment_stats import compute_portfolio_overview


def _shift_months(d: date, k: int) -> date:
    m0 = d.month + k - 1
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


async def finance_snapshot(db: AsyncSession, user_id: str) -> dict:
    snap: dict = {"as_of": date.today().isoformat()}

    # ---- 近 12 个月月度收支 ----
    rows = (await db.execute(text(
        """
        SELECT substr(date,1,7) AS ym, type, SUM(amount) AS total
        FROM transactions
        WHERE user_id=:u AND date >= :begin
        GROUP BY ym, type ORDER BY ym
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=400)).isoformat()})).all()
    monthly: dict[str, dict] = {}
    for ym, ttype, total in rows:
        monthly.setdefault(ym, {"income": 0.0, "expense": 0.0, "transfer": 0.0})[ttype] = float(total or 0)
    for ym in list(monthly):
        d = monthly[ym]
        d["net"] = d["income"] - d["expense"]
        d["to_invest"] = d["transfer"]
    snap["monthly_12m"] = dict(sorted(monthly.items())[-12:])

    # ---- 储蓄率与时间窗口（滚动日历月，与统计 tab 同口径）----
    async def _window_sums(begin: date) -> tuple[float, float]:
        r = (await db.execute(text(
            """
            SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END),0)
            FROM transactions
            WHERE user_id=:u AND type IN ('income','expense') AND date >= :b
            """
        ), {"u": user_id, "b": begin.isoformat()})).one()
        return float(r[0] or 0), float(r[1] or 0)

    inc6, exp6 = await _window_sums(_shift_months(date.today(), -6))
    snap["savings_6m"] = {
        "income": round(inc6, 2), "expense": round(exp6, 2),
        "net": round(inc6 - exp6, 2),
        "savings_rate": round((inc6 - exp6) / inc6, 4) if inc6 > 0 else None,
    }

    # ---- 最近 90 天分类支出 Top ----
    cat_rows = (await db.execute(text(
        """
        SELECT c.name, SUM(t.amount) AS total, COUNT(*) AS n
        FROM transactions t JOIN categories c ON c.id = t.category_id
        WHERE t.user_id=:u AND t.type='expense' AND t.date >= :begin
        GROUP BY c.name ORDER BY total DESC LIMIT 12
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=90)).isoformat()})).all()
    exp90 = sum(float(r[1]) for r in cat_rows)
    snap["expense_90d_by_category"] = [
        {"category": r[0], "total": round(float(r[1]), 2),
         "share": round(float(r[1]) / exp90, 4) if exp90 else None, "count": r[2]}
        for r in cat_rows
    ]
    snap["expense_90d_total"] = round(exp90, 2)

    # ---- 账户余额（期初 + 收 - 支 + 转入 - 转出）----
    acc_rows = (await db.execute(text(
        """
        SELECT a.id, a.name, a.account_type, a.initial_balance,
          COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id AND t.type='income'),0) +
          COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.dest_account_id=a.id AND t.type='transfer'),0)
          - COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id AND t.type='expense'),0)
          - COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id AND t.type='transfer'),0)
          AS balance
        FROM accounts a WHERE a.user_id=:u AND a.hidden=0
        """
    ), {"u": user_id})).all()
    snap["accounts"] = [
        {"name": r[1], "type": r[2], "balance": round(float(r[4]), 2)}
        for r in acc_rows
    ]
    cash_total = sum(x["balance"] for x in snap["accounts"] if x["type"] != "investment")
    snap["cash_total"] = round(cash_total, 2)

    # ---- 投资组合 ----
    inv_rows = (await db.execute(text(
        """
        SELECT name, investment_type, quantity, purchase_price, current_price,
               COALESCE(symbol,''), is_money_market, purchase_date
        FROM investments
        WHERE user_id=:u AND (sell_date IS NULL OR sell_date='')
        """
    ), {"u": user_id})).all()
    positions, total_cost, total_value = [], 0.0, 0.0
    for name, itype, qty, buy, cur, sym, mm, pdate in inv_rows:
        qty = float(qty or 0)
        cost = qty * float(buy or 0)
        value = qty * float(cur or buy or 0)
        total_cost += cost
        total_value += value
        positions.append({
            "name": name, "type": itype, "symbol": sym,
            "cost": round(cost, 2), "value": round(value, 2),
            "pnl": round(value - cost, 2),
            "pnl_pct": round((value - cost) / cost, 4) if cost > 0 else None,
            "money_market": bool(mm),
        })
    positions.sort(key=lambda x: -x["value"])
    snap["portfolio"] = {
        "positions": positions[:15],
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_value - total_cost, 2),
        "total_pnl_pct": round((total_value - total_cost) / total_cost, 4) if total_cost > 0 else None,
    }

    # ---- 应急储备（唯一口径：与首页共用 emergency_reserve 服务）----
    # 旧口径把投资账户余额 + 持仓市值 + 固定资产都算进"可动用应急资金"，
    # 导致长期投资资金被重复充当应急储备（2026-09-04 修正）。
    snap["emergency_reserve"] = await compute_emergency_reserve(db, user_id)

    # ---- 时间尺度快照（6/3/1 月收支对比，滚动日历月精确区间） ----
    async def _month_window(months_back: int) -> dict:
        inc, exp = await _window_sums(_shift_months(date.today(), -months_back))
        return {
            "income": round(inc, 2),
            "expense": round(exp, 2),
            "net": round(inc - exp, 2),
            "savings_rate": round((inc - exp) / inc, 4) if inc > 0 else None,
            "monthly_avg": round((inc - exp) / max(1, months_back), 2),
        }

    snap["time_windows"] = {
        "6m": await _month_window(6),
        "3m": await _month_window(3),
        "1m": await _month_window(1),
    }

    # ---- 收入画像（按记账分类聚合，未选分类的归"未分类"） ----
    inc_rows = (await db.execute(text(
        """
        SELECT substr(t.date,1,7) AS ym, COALESCE(c.name,'未分类') AS cat, t.amount
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id=:u AND t.type='income' AND t.date >= :begin
          AND COALESCE(t.description,'') NOT LIKE '投资月度盈亏%'
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).all()
    # 投资账户的「投资月度盈亏 YYYY-MM」是系统 sync 自动写入的浮动盈亏流水，
    # 不是真实现金收入（盈亏已体现在持仓市值中）。计入收入结构会污染
    # 收入画像——投资 tab 自身统计分红时本就排除它（2026-09-04 对齐该口径）。
    pnl_rows = (await db.execute(text(
        """
        SELECT COALESCE(SUM(t.amount),0)
        FROM transactions t
        WHERE t.user_id=:u AND t.type='income' AND t.date >= :begin
          AND t.description LIKE '投资月度盈亏%'
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).one()
    cat_total: Counter[str] = Counter()
    cat_month_sum: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    inc_total = 0.0
    inc_count = 0
    for ym, cat, amt in inc_rows:
        a = float(amt or 0)
        cat_total[cat] += a
        cat_month_sum[cat][ym] += a
        inc_total += a
        inc_count += 1
    by_subcategory = {}
    for cat, tot in cat_total.items():
        month_vals = list(cat_month_sum[cat].values())
        mean = sum(month_vals) / len(month_vals)
        sd = (sum((x - mean) ** 2 for x in month_vals) / len(month_vals)) ** 0.5 if len(month_vals) > 1 else 0.0
        by_subcategory[cat] = {
            "total_12m": round(tot, 2),
            "share": round(tot / inc_total, 4) if inc_total > 0 else None,
            "monthly_avg": round(mean, 2),
            "monthly_std": round(sd, 2),
            "coefficient_of_variation": round(sd / mean, 3) if mean > 0 else None,
            "months_active": len(month_vals),
        }
    snap["income_profile"] = {
        "12m_total": round(inc_total, 2),
        "12m_count": inc_count,
        "by_subcategory": dict(sorted(by_subcategory.items(), key=lambda kv: -(kv[1]["total_12m"] or 0))),
        # 口径说明：让 AI 明确知道哪些钱不算"收入"，避免它再去质疑数据
        "excluded": {
            "investment_pnl_sync_12m": round(float(pnl_rows[0] or 0), 2),
            "reason": "已排除系统 sync 写入的「投资月度盈亏」流水：属浮动盈亏入账，"
                      "非真实现金收入，且盈亏已体现在持仓市值中（重复计入会虚增收入）",
        },
    }

    # ---- 投资画像（决策画像：买卖流水 + 当前持仓 + 建仓节奏） ----
    tx_rows = (await db.execute(text(
        """
        SELECT event_date, event_type, COALESCE(amount,0),
               COALESCE(quantity,0), COALESCE(unit_price,0), COALESCE(fee,0)
        FROM investment_transactions
        WHERE user_id=:u AND event_type IN ('buy','sell') AND event_date >= :begin
        ORDER BY event_date
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).all()
    # 建仓节奏（新建标的：按 investments.purchase_date 计）
    build_rows = (await db.execute(text(
        """
        SELECT substr(purchase_date, 1, 7) AS ym, COUNT(*) AS n
        FROM investments WHERE user_id=:u
          AND purchase_date IS NOT NULL AND purchase_date >= :begin
        GROUP BY ym ORDER BY ym
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).all()
    build_by_month = {ym: int(n) for ym, n in build_rows}
    # 调仓节奏（按月统计买卖动作笔数）
    trade_by_month: dict[str, dict[str, int]] = defaultdict(lambda: {"buy": 0, "sell": 0})
    for ev_date, ev_type, *_ in tx_rows:
        trade_by_month[str(ev_date)[:7]][ev_type] += 1
    po = await compute_portfolio_overview(db, user_id)
    snap["investment_profile"] = {
        "realized_pnl": po.realized_pnl,
        "floating_pnl": po.floating_pnl,
        "xirr_annualized_pct": round(po.xirr_annualized * 100, 2) if po.xirr_annualized is not None else None,
        "total_deposits": po.total_deposits,
        "total_withdrawals": po.total_withdrawals,
        "12m_tx_count": len(tx_rows),
        "12m_buy_count": sum(1 for x in tx_rows if x[1] == "buy"),
        "12m_sell_count": sum(1 for x in tx_rows if x[1] == "sell"),
        "12m_buy_amount": round(sum(abs(float(x[2] or 0)) for x in tx_rows if x[1] == "buy"), 2),
        "12m_sell_amount": round(sum(abs(float(x[2] or 0)) for x in tx_rows if x[1] == "sell"), 2),
        "12m_trade_by_month": {k: dict(v) for k, v in sorted(trade_by_month.items())},
        "12m_active_trade_months": len(trade_by_month),
        "12m_new_positions_by_month": build_by_month,
        "data_source": "investment_transactions",
        "current_position_count": len(positions),
        "current_total_value": round(total_value, 2),
        "current_total_pnl": round(total_value - total_cost, 2),
        "current_top1_concentration": round(positions[0]["value"] / total_value, 4) if positions and total_value > 0 else None,
        "current_top5_concentration": round(sum(p["value"] for p in positions[:5]) / total_value, 4) if positions and total_value > 0 else None,
        "top3_positions": [
            {"name": p["name"], "value": p["value"],
             "share": round(p["value"] / total_value, 4) if total_value > 0 else None}
            for p in positions[:3]
        ],
    }

    # ---- 支出节奏（异常大额 + 最近 30 天） ----
    daily_exp = (await db.execute(text(
        """
        SELECT date, SUM(amount) AS total
        FROM transactions
        WHERE user_id=:u AND type='expense' AND date >= :begin
        GROUP BY date ORDER BY date
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=180)).isoformat()})).all()
    amounts = [float(d[1] or 0) for d in daily_exp]
    if amounts:
        mean_d = sum(amounts) / len(amounts)
        std_d = (sum((x - mean_d) ** 2 for x in amounts) / (len(amounts) - 1)) ** 0.5 if len(amounts) > 1 else 0
        threshold = mean_d + 2 * std_d
        unusual = sorted(
            [{"date": d[0], "amount": round(float(d[1] or 0), 2)}
             for d in daily_exp if float(d[1] or 0) > threshold],
            key=lambda x: -x["amount"]
        )[:8]
    else:
        mean_d = std_d = threshold = 0
        unusual = []
    last30 = [d for d in daily_exp if d[0] >= (date.today() - timedelta(days=30)).isoformat()]
    last30_total = sum(float(d[1] or 0) for d in last30)
    snap["expense_rhythm"] = {
        "180d_daily_mean": round(mean_d, 2),
        "180d_daily_std": round(std_d, 2),
        "anomaly_threshold_2sigma": round(threshold, 2),
        "unusual_days": unusual,
        "last30d_total": round(last30_total, 2),
        "last30d_daily_avg": round(last30_total / max(1, len(last30)), 2),
        "biggest_day_180d": {"date": daily_exp[0][0], "amount": round(float(daily_exp[0][1] or 0), 2)} if daily_exp else None,
    }

    # ---- 风险敞口 ----
    invest_value = total_value
    grand_total = cash_total + invest_value
    cash_share = round(cash_total / grand_total, 4) if grand_total > 0 else None
    invest_share = round(invest_value / grand_total, 4) if grand_total > 0 else None
    snap["risk_exposure"] = {
        "total_assets": round(grand_total, 2),
        "cash_total": round(cash_total, 2),
        "invest_total": round(invest_value, 2),
        "cash_share": cash_share,
        "invest_share": invest_share,
        "emergency_cover_months": snap["emergency_reserve"]["cover_months"],
        "top1_position_share": round(positions[0]["value"] / invest_value, 4) if positions and invest_value > 0 else None,
        "top1_position_name": positions[0]["name"] if positions else None,
        "top3_concentration": round(sum(p["value"] for p in positions[:3]) / invest_value, 4) if positions and invest_value > 0 else None,
        "top5_concentration": round(sum(p["value"] for p in positions[:5]) / invest_value, 4) if positions and invest_value > 0 else None,
        "money_market_share": round(sum(p["value"] for p in positions if p["money_market"]) / invest_value, 4)
            if invest_value > 0 and any(p["money_market"] for p in positions) else None,
    }

    # ---- 投资账户对账（让 AI 能自证勾稽，回应"无法勾稽=假数据"的质疑）----
    # 恒等式：投资账户余额 = 累计入金 − 累计出金 + 累计已入账盈亏
    # 其中"累计已入账盈亏"是 sync 写入的「投资月度盈亏」流水，代表浮动盈亏入账。
    # 三项都能对上时，AI 不应再质疑数据的内部一致性。
    try:
        cf_rows = (await db.execute(text(
            "SELECT flow_type, COALESCE(SUM(amount),0) FROM investment_cash_flows "
            "WHERE user_id=:u GROUP BY flow_type"
        ), {"u": user_id})).all()
        cf = {r[0]: float(r[1] or 0) for r in cf_rows}
        dep_total, wd_total = cf.get("deposit", 0.0), cf.get("withdrawal", 0.0)
        inv_acc_bal = sum(x["balance"] for x in snap["accounts"] if x["type"] == "investment")
        posted_pnl = float((await db.execute(text(
            """
            SELECT COALESCE(SUM(t.amount),0) FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.user_id=:u AND t.type='income' AND a.account_type='investment'
              AND t.description LIKE '投资月度盈亏%'
            """
        ), {"u": user_id})).one()[0] or 0)
        expected = dep_total - wd_total + posted_pnl
        diff = round(inv_acc_bal - expected, 2) + 0.0   # +0.0 归一 -0.0
        snap["investment_reconciliation"] = {
            "identity": "投资账户余额 = 累计入金 − 累计出金 + 累计已入账盈亏",
            "total_deposits": round(dep_total, 2),
            "total_withdrawals": round(wd_total, 2),
            "net_principal": round(dep_total - wd_total, 2),
            "cumulative_pnl_posted": round(posted_pnl, 2),
            "investment_account_balance": round(inv_acc_bal, 2),
            "expected_balance": round(expected, 2),
            "difference": diff,
            "balanced": abs(diff) < 0.01,
            "note": "差额为 0 表示台账与账户余额完全勾稽；不为 0 时差额即"
                    "待补记的出/入金（多为投资账户↔工资账户转账未同步）。",
        }
    except Exception:
        snap["investment_reconciliation"] = {"note": "台账表缺失，无法勾稽"}

    # ---- 购房目标画像（参数可在 AI 咨询页编辑） ----
    plan = await get_housing_plan(db, user_id)
    snap["housing_profile"] = build_housing_snapshot(plan)

    return snap
