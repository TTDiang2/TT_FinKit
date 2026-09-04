"""应急储备口径（唯一事实来源）。

首页「紧急储备」与 AI 咨询 tab「应急覆盖月数」必须同源，曾经两处各算各的、
且都把投资账户余额/持仓市值算进应急储备——2026-09-04 统一口径。

## 口径定义（与用户确认）
- **只算现金类账户**（account_type='cash' 且未隐藏）：消费账户、工资账户等
- **排除投资账户余额**：那是长期投资资金，不能同时充当应急储备（双重记账风险）
- **排除持仓市值 / 固定资产 / 负债**：不具备 T+0 流动性，且计入会虚高覆盖月数
- 月均支出 = 近 3 个**完整自然月**的支出均值（不含当月，当月未结束）

公式：cover_months = 现金类账户余额合计 ÷ 近3月月均支出
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_TARGET_MONTHS = 6.0


def _shift_months(d: date, k: int) -> date:
    m0 = d.month + k - 1
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


async def compute_emergency_reserve(
    db: AsyncSession,
    user_id: str,
    target_months: float = DEFAULT_TARGET_MONTHS,
) -> dict:
    """返回应急储备口径的统一计算结果。"""
    today = date.today()
    m1_start = today.replace(day=1)

    # ---- 近 3 个完整自然月支出 ----
    exp3_sum = 0.0
    months_used: list[str] = []
    for i in range(1, 4):
        ms, me = _shift_months(m1_start, -i), _shift_months(m1_start, -(i - 1))
        r = (await db.execute(text(
            "SELECT COALESCE(SUM(amount),0) FROM transactions "
            "WHERE user_id=:u AND type='expense' AND date >= :s AND date < :e"
        ), {"u": user_id, "s": ms.isoformat(), "e": me.isoformat()})).one()
        exp3_sum += float(r[0] or 0)
        months_used.append(ms.strftime("%Y-%m"))
    avg3 = exp3_sum / 3.0

    # ---- 现金类账户余额（逐账户，便于前端/AI 溯源） ----
    rows = (await db.execute(text(
        """
        SELECT a.name, a.account_type,
          a.initial_balance
          + COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id AND t.type='income'),0)
          + COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.dest_account_id=a.id AND t.type='transfer'),0)
          - COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id AND t.type='expense'),0)
          - COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id AND t.type='transfer'),0)
          AS balance
        FROM accounts a
        WHERE a.user_id=:u AND a.hidden=0
        ORDER BY balance DESC
        """
    ), {"u": user_id})).all()

    included, excluded = [], []
    for name, atype, bal in rows:
        bal = float(bal or 0)
        item = {"name": name, "type": atype, "balance": round(bal, 2)}
        if atype == "cash":
            included.append(item)
        else:
            excluded.append(item)

    liquid_cash = sum(x["balance"] for x in included)
    target_amount = avg3 * target_months
    cover = round(liquid_cash / avg3, 2) if avg3 > 0 else None

    return {
        # 口径说明写进返回值，AI 直接引用，避免它再自行把投资资金算进来
        "definition": "现金类账户（account_type=cash，不含隐藏账户）余额合计；"
                      "已排除投资账户余额与持仓市值——长期投资资金不得同时充当应急储备",
        "liquid_cash": round(liquid_cash, 2),
        "avg_monthly_expense_3m": round(avg3, 2),
        "months_used": months_used,
        "cover_months": cover,
        "target_months": target_months,
        "target_amount": round(target_amount, 2),
        "gap": round(liquid_cash - target_amount, 2),
        "included_accounts": included,
        "excluded_accounts": excluded,
        "excluded_note": "以下账户按口径不计入应急储备：" +
                         ("、".join(f"{x['name']}({x['balance']:.2f})" for x in excluded)
                          or "无"),
    }
