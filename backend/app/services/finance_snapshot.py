"""AI 咨询 — 真实财务数据聚合。

把记账（收入/支出/转账）、账户余额、投资持仓聚合成一份结构化快照，
作为 AI（严厉财富审计师人设）的事实依据。所有数字都来自真实表，
AI 只被允许引用这份快照里的数字。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
               COALESCE(symbol,''), is_money_market
        FROM investments
        WHERE user_id=:u AND sell_date IS NULL OR sell_date=''
        """
    ), {"u": user_id})).all()
    positions, total_cost, total_value = [], 0.0, 0.0
    for name, itype, qty, buy, cur, sym, mm in inv_rows:
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
    return snap
