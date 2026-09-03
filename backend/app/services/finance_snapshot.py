"""AI 咨询 — 真实财务数据聚合。

把记账（收入/支出/转账）、账户余额、投资持仓聚合成一份结构化快照，
作为 AI（严厉财富审计师人设）的事实依据。所有数字都来自真实表，
AI 只被允许引用这份快照里的数字。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------- 快照扩展（用户拍板 2026-09-03） ----------------
# 6 个数据块：时间尺度 / 收入画像 / 投资画像 / 经营储蓄率 / 支出节奏 / 风险敞口。
# 排除应收应付与目标进度。

_M_KEYWORDS_BY_NOTE = [
    # note 关键词 → 收入子分类（中文匹配，命中首条为准）
    ("奖金", "奖金"), ("补贴", "补贴"), ("津贴", "补贴"),
    ("报销", "报销"), ("理财", "理财收益"), ("利息", "理财收益"),
    ("红包", "其他"), ("退款", "其他"), ("兼职", "兼职"),
]


def _income_subcategory(note: str | None) -> str:
    if not note:
        return "工资"
    for kw, cat in _M_KEYWORDS_BY_NOTE:
        if kw in note:
            return cat
    return "工资"


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

    # ---- 储蓄率（近 6 个月，剔除转账）----
    inc6 = sum(m["income"] for ym, m in monthly.items() if ym >= (date.today() - timedelta(days=200)).strftime("%Y-%m"))
    exp6 = sum(m["expense"] for ym, m in monthly.items() if ym >= (date.today() - timedelta(days=200)).strftime("%Y-%m"))
    snap["savings_6m"] = {
        "income": round(inc6, 2), "expense": round(exp6, 2),
        "net": round(inc6 - exp6, 2),
        "savings_rate": round((inc6 - exp6) / inc6, 4) if inc6 > 0 else None,
    }

    # ---- 经营储蓄率（剔除转账后的真实烧钱率） ----
    # 把 transfer 当中性资金搬运，储蓄率只看 income vs expense
    operating_inc6 = sum(m["income"] for ym, m in monthly.items() if ym >= (date.today() - timedelta(days=200)).strftime("%Y-%m"))
    operating_exp6 = sum(m["expense"] for ym, m in monthly.items() if ym >= (date.today() - timedelta(days=200)).strftime("%Y-%m"))
    snap["operating_savings_6m"] = {
        "income": round(operating_inc6, 2),
        "expense": round(operating_exp6, 2),
        "net": round(operating_inc6 - operating_exp6, 2),
        # 经营储蓄率不计算百分比（含义模糊——负值代表入不敷出）
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

    # ---- 应急储备估算 ----
    avg_exp = exp6 / 6 if exp6 > 0 else None
    snap["emergency_reserve"] = {
        "cash_total": snap["cash_total"],
        "avg_monthly_expense": round(avg_exp, 2) if avg_exp else None,
        "cover_months": round(cash_total / avg_exp, 1) if avg_exp and avg_exp > 0 else None,
    }

    # ---- 时间尺度快照（6/3/1 月收支对比） ----
    # 每月净支出 = expense - income（不含 transfer）；月储蓄率 = 1 - expense/income
    def _month_window(months_back: int) -> dict:
        cutoff = (date.today().replace(day=1) - timedelta(days=months_back * 31)).replace(day=1)
        inc = sum(m["income"] for ym, m in monthly.items() if ym >= cutoff.strftime("%Y-%m"))
        exp = sum(m["expense"] for ym, m in monthly.items() if ym >= cutoff.strftime("%Y-%m"))
        return {
            "income": round(inc, 2),
            "expense": round(exp, 2),
            "net": round(inc - exp, 2),
            "savings_rate": round((inc - exp) / inc, 4) if inc > 0 else None,
            "monthly_avg": round((inc - exp) / max(1, months_back), 2),
        }
    snap["time_windows"] = {
        "6m": _month_window(6),
        "3m": _month_window(3),
        "1m": _month_window(1),
    }

    # ---- 收入画像（结构 + 稳定性 + 趋势） ----
    inc_rows = (await db.execute(text(
        """
        SELECT substr(date, 1, 7) AS ym, amount, COALESCE(description,'')
        FROM transactions
        WHERE user_id=:u AND type='income' AND date >= :begin
        ORDER BY date
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).all()
    sub_totals: Counter[str] = Counter()
    sub_months: dict[str, set[str]] = defaultdict(set)
    inc_total = 0.0
    inc_count = 0
    for ym, amt, note in inc_rows:
        c = _income_subcategory(note)
        sub_totals[c] += float(amt or 0)
        sub_months[c].add(ym)
        inc_total += float(amt or 0)
        inc_count += 1
    sub_avg = {k: round(v / max(1, len(sub_months[k])), 2) for k, v in sub_totals.items()}
    sub_std = {}
    for k in sub_totals:
        months_active = len(sub_months[k])
        avg = sub_avg[k]
        # 月波动（最大/平均倍率）
        rows_k = [float(a) for (y, a, _n) in inc_rows if _income_subcategory(_n) == k]
        if len(rows_k) > 1:
            mean = sum(rows_k) / len(rows_k)
            var = sum((x - mean) ** 2 for x in rows_k) / (len(rows_k) - 1)
            sd = var ** 0.5
            sub_std[k] = {
                "monthly_avg": round(mean, 2),
                "monthly_std": round(sd, 2),
                "coefficient_of_variation": round(sd / mean, 3) if mean > 0 else None,
                "months_active": months_active,
            }
    snap["income_profile"] = {
        "12m_total": round(inc_total, 2),
        "12m_count": inc_count,
        "by_subcategory": {
            k: {
                "total_12m": round(v, 2),
                "share": round(v / inc_total, 4) if inc_total > 0 else None,
                **sub_std.get(k, {"monthly_avg": sub_avg.get(k)}),
            } for k, v in sub_totals.most_common()
        },
    }

    # ---- 投资画像（决策画像：买卖流水 + 当前持仓 + 建仓节奏） ----
    tx_rows = (await db.execute(text(
        """
        SELECT date, type, amount, COALESCE(description,''), account_type
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE t.user_id=:u AND t.type IN ('buy','sell')
          AND date >= :begin
        ORDER BY date
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).all()
    # 建仓节奏（按月统计建仓动作）
    build_rows = (await db.execute(text(
        """
        SELECT substr(purchase_date, 1, 7) AS ym, COUNT(*) AS n
        FROM investments WHERE user_id=:u
          AND purchase_date IS NOT NULL AND purchase_date >= :begin
        GROUP BY ym ORDER BY ym
        """
    ), {"u": user_id, "begin": (date.today() - timedelta(days=365)).isoformat()})).all()
    build_by_month = {ym: int(n) for ym, n in build_rows}
    snap["investment_profile"] = {
        "12m_tx_count": len(tx_rows),
        "12m_buy_count": sum(1 for x in tx_rows if x[1] == "buy"),
        "12m_sell_count": sum(1 for x in tx_rows if x[1] == "sell"),
        "12m_buy_amount": round(sum(float(x[2] or 0) for x in tx_rows if x[1] == "buy"), 2),
        "12m_sell_amount": round(sum(float(x[2] or 0) for x in tx_rows if x[1] == "sell"), 2),
        "12m_new_positions_by_month": build_by_month,
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

    return snap
