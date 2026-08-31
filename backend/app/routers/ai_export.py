import io
import zipfile
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import get_private_db
from ..models.transaction import Transaction
from ..models.account import Account
from ..models.category import Category
from ..models.asset import Asset
from ..models.investment import Investment
from ..models.user_settings import UserSettings
from ..models.report_archive import ReportArchive
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/ai", tags=["ai"])

AI_GUIDE_MD = """# FinKit AI 数据分析指南

## 数据结构说明

你收到的 `finkit-data.json` 包含以下模块：

### 1. user_profile（用户画像）
- `currency`: 货币符号
- `accounts`: 所有账户列表（name, type, balance）
- `categories`: 所有分类（name, type, is_necessary）

### 2. statistics（统计数据）
- `overview`: 当月概览（total_assets, current_month_income/expense/net）
- `monthly_trend`: 近12个月收支趋势（month, income, expense, net）
- `category_breakdown`: 近3个月分类汇总
  - `income`: [{name, total}] 收入分类
  - `expense`: [{name, total}] 支出分类

### 3. reports（财务报表）
- `latest_pl`: 当月利润表
  - `main_income/other_income`: 主营/其他收入明细
  - `main_cost/other_cost`: 主营/其他成本明细
  - `gross_profit/gross_margin`: 毛利/毛利率
  - `net_income/net_margin`: 净利/净利率
- `latest_bs`: 资产负债表快照
  - `assets`: {cash, investment_accounts, fixed_assets, other_assets, investment_assets}
  - `total_assets, liabilities, net_worth`
- `latest_cf`: 当月现金流量表
  - `operating/investing/financing`: 经营/投资/筹资活动
  - `net_cash_flow`: 净现金流
- `archived_reports`: 用户选择包含的已归档报表（如有）

### 4. investments（投资组合）
- `portfolio`: 每个持仓（name, type, quantity, purchase_price, current_price, profit_loss）
- `total_invested/total_current/total_pnl`: 汇总

### 5. transactions_sample（交易样本）
- `recent_30_days`: 近30天交易（date, type, amount, description, category, account）
- `top_expenses_3_months`: 近3个月最大10笔支出

---

## 分析要求

请基于以上数据，提供以下分析：

### A. 财务健康诊断
1. 用通俗易懂的语言解读三张报表（利润表、资产负债表、现金流量表）
2. 计算并评估关键财务比率：储蓄率、资产负债率、流动性比率
3. 判断当前财务状况：健康/需注意/警告，给出理由

### B. 收支分析
1. 分析近12个月的收支趋势，识别季节性规律
2. 支出结构分析：哪些是必要支出、哪些可优化
3. 指出异常支出模式（如某月突然大额支出）
4. 与同收入水平的一般性建议做对比

### C. 预算建议
1. 基于历史数据，给出下月各分类预算建议
2. 设定合理的储蓄目标
3. 标记需要控制支出的领域

### D. 投资评估（如有投资数据）
1. 评估当前投资组合的表现
2. 计算综合收益率并与市场基准比较
3. 提出资产配置优化建议

### E. 财务规划
1. 短期（1-3月）：可执行的改进行动
2. 中期（3-12月）：财务目标建议
3. 长期：基于当前趋势的展望

### 输出格式
- 使用中文
- 数据驱动，引用具体数字
- 突出关键发现（用加粗或列表）
- 建议要具体、可操作，不要泛泛而谈
- 如数据不足以判断，请明确指出
"""


@router.post("/export-package")
async def export_package(
    archive_ids: List[str] = Body(default=[]),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    current_month_start = f"{now.year}-{now.month:02d}-01"
    three_months_ago_month = now.month - 3
    three_months_ago_year = now.year
    while three_months_ago_month <= 0:
        three_months_ago_month += 12
        three_months_ago_year -= 1
    recent_start = f"{three_months_ago_year}-{three_months_ago_month:02d}-01"

    settings_result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = settings_result.scalars().first()
    currency = settings.currency_symbol if settings else "¥"

    accounts_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = accounts_result.scalars().all()

    categories_result = await db.execute(select(Category).where(Category.user_id == user_id))
    categories = categories_result.scalars().all()

    month_inc_res = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income",
            Transaction.date >= current_month_start
        )
    )
    month_exp_res = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date >= current_month_start
        )
    )
    month_income = float(month_inc_res.scalar() or 0)
    month_expense = float(month_exp_res.scalar() or 0)
    total_assets = sum(a.initial_balance for a in accounts) + month_income - month_expense

    monthly_trend = []
    for i in range(11, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        if m_month == 12:
            period_end = f"{m_year + 1}-01-01"
        else:
            period_end = f"{m_year}-{m_month + 1:02d}-01"
        period_start = f"{m_year}-{m_month:02d}-01"

        inc_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date >= period_start, Transaction.date < period_end
            )
        )
        exp_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= period_start, Transaction.date < period_end
            )
        )
        inc_val = float(inc_res.scalar() or 0)
        exp_val = float(exp_res.scalar() or 0)
        monthly_trend.append({
            "month": f"{m_year}-{m_month:02d}",
            "income": round(inc_val, 2),
            "expense": round(exp_val, 2),
            "net": round(inc_val - exp_val, 2)
        })

    income_cats_result = await db.execute(
        select(Category.name, Category.color, func.sum(Transaction.amount).label("total"))
        .join(Transaction, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user_id, Transaction.type == "income",
               Transaction.date >= recent_start)
        .group_by(Category.name, Category.color)
    )
    income_cats = [{"name": r[0], "total": round(float(r[2]), 2)} for r in income_cats_result.all()]

    expense_cats_result = await db.execute(
        select(Category.name, Category.color, func.sum(Transaction.amount).label("total"))
        .join(Transaction, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user_id, Transaction.type == "expense",
               Transaction.date >= recent_start)
        .group_by(Category.name, Category.color)
    )
    expense_cats = [{"name": r[0], "total": round(float(r[2]), 2)} for r in expense_cats_result.all()]

    pl_data = await _build_pl(user_id, db, now.year, now.month)
    bs_data = await _build_bs(user_id, db, now.year, now.month)
    cf_data = await _build_cf(user_id, db, now.year, now.month)

    archived_reports = []
    if archive_ids:
        arc_result = await db.execute(
            select(ReportArchive).where(
                ReportArchive.user_id == user_id,
                ReportArchive.id.in_(archive_ids)
            )
        )
        for arc in arc_result.scalars().all():
            content = arc.content if isinstance(arc.content, dict) else json.loads(arc.content) if arc.content else {}
            archived_reports.append({
                "report_type": arc.report_type,
                "period_start": arc.period_start,
                "period_end": arc.period_end,
                "generated_at": str(arc.generated_at),
                "content": content
            })

    inv_result = await db.execute(select(Investment).where(Investment.user_id == user_id))
    investments = inv_result.scalars().all()
    active_investments = [i for i in investments if not i.sell_date]
    total_invested = sum(i.purchase_price * i.quantity for i in active_investments)
    total_current = sum(i.current_price * i.quantity for i in active_investments)

    thirty_ago = (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)).strftime("%Y-%m-%d")
    recent_txns_result = await db.execute(
        select(Transaction, Category.name.label("cat_name"))
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user_id, Transaction.date >= thirty_ago)
        .order_by(Transaction.date.desc())
        .limit(100)
    )
    acc_map = {a.id: a.name for a in accounts}
    recent_txns = []
    for row in recent_txns_result.all():
        t = row[0]
        recent_txns.append({
            "date": t.date, "type": t.type, "amount": round(t.amount, 2),
            "description": t.description or "", "category": row[1] or "",
            "account": acc_map.get(t.account_id, "")
        })

    top_exp_result = await db.execute(
        select(Transaction, Category.name.label("cat_name"))
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user_id, Transaction.type == "expense",
               Transaction.date >= recent_start)
        .order_by(Transaction.amount.desc())
        .limit(10)
    )
    top_expenses = []
    for row in top_exp_result.all():
        t = row[0]
        top_expenses.append({
            "date": t.date, "amount": round(t.amount, 2),
            "description": t.description or "", "category": row[1] or "",
            "account": acc_map.get(t.account_id, "")
        })

    package = {
        "export_date": now.strftime("%Y-%m-%d"),
        "user_profile": {
            "currency": currency,
            "accounts": [{"name": a.name, "type": a.account_type or "cash", "balance": round(a.initial_balance, 2)} for a in accounts],
            "categories": [{"name": c.name, "type": c.type, "is_necessary": c.is_necessary or False} for c in categories]
        },
        "statistics": {
            "overview": {
                "total_assets": round(total_assets, 2),
                "current_month_income": round(month_income, 2),
                "current_month_expense": round(month_expense, 2),
                "current_month_net": round(month_income - month_expense, 2)
            },
            "monthly_trend": monthly_trend,
            "category_breakdown": {"income": income_cats, "expense": expense_cats}
        },
        "reports": {
            "latest_pl": pl_data,
            "latest_bs": bs_data,
            "latest_cf": cf_data,
            "archived_reports": archived_reports
        },
        "investments": {
            "portfolio": [{
                "name": i.name, "type": i.investment_type,
                "quantity": i.quantity, "purchase_price": round(i.purchase_price, 2),
                "current_price": round(i.current_price, 2),
                "profit_loss": round((i.current_price - i.purchase_price) * i.quantity, 2)
            } for i in active_investments],
            "total_invested": round(total_invested, 2),
            "total_current": round(total_current, 2),
            "total_pnl": round(total_current - total_invested, 2)
        },
        "transactions_sample": {
            "recent_30_days": recent_txns,
            "top_expenses_3_months": top_expenses
        }
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("finkit-data.json", json.dumps(package, ensure_ascii=False, indent=2))
        zf.writestr("AI-GUIDE.md", AI_GUIDE_MD)
    zip_buffer.seek(0)

    filename = f"finkit-export-{now.strftime('%Y%m%d')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


async def _build_pl(user_id: str, db: AsyncSession, year: int, month: int) -> dict:
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    txn_result = await db.execute(
        select(Transaction.category_id, Transaction.type, func.sum(Transaction.amount).label("total"))
        .where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.category_id, Transaction.type)
    )
    txn_rows = txn_result.all()

    cat_ids = [r[0] for r in txn_rows if r[0]]
    cat_map = {}
    if cat_ids:
        cats_result = await db.execute(select(Category).where(Category.id.in_(cat_ids)))
        cat_map = {c.id: c for c in cats_result.scalars().all()}

    sections = {"main_income": [], "other_income": [], "main_cost": [], "other_cost": []}
    totals = {"main_income": 0.0, "other_income": 0.0, "main_cost": 0.0, "other_cost": 0.0}

    for cat_id, txn_type, total in txn_rows:
        amount = round(float(total), 2)
        if amount == 0:
            continue
        cat = cat_map.get(cat_id)
        cat_name = cat.name if cat else "未知"
        pl = cat.pl_section if cat else ""

        if txn_type == "income":
            if pl == "exclude_income":
                continue
            key = "other_income" if pl == "other_income" else "main_income"
        elif txn_type == "expense":
            if pl == "exclude_expense":
                continue
            key = "other_cost" if pl == "other_cost" else "main_cost"
        else:
            continue

        sections[key].append({"name": cat_name, "total": amount})
        totals[key] += amount

    total_income = totals["main_income"] + totals["other_income"]
    total_expense = totals["main_cost"] + totals["other_cost"]
    gross_profit = totals["main_income"] - totals["main_cost"]
    return {
        "period": f"{year}-{month:02d}",
        "main_income": sections["main_income"], "total_main_income": round(totals["main_income"], 2),
        "other_income": sections["other_income"], "total_other_income": round(totals["other_income"], 2),
        "main_cost": sections["main_cost"], "total_main_cost": round(totals["main_cost"], 2),
        "other_cost": sections["other_cost"], "total_other_cost": round(totals["other_cost"], 2),
        "total_income": round(total_income, 2), "total_expense": round(total_expense, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin": round(gross_profit / totals["main_income"] * 100, 1) if totals["main_income"] > 0 else 0,
        "net_income": round(total_income - total_expense, 2),
        "net_margin": round((total_income - total_expense) / total_income * 100, 1) if total_income > 0 else 0
    }


async def _build_bs(user_id: str, db: AsyncSession, year: int, month: int) -> dict:
    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()
    cash_accounts = [a for a in accounts if (a.account_type or "cash") == "cash"]
    inv_accounts = [a for a in accounts if (a.account_type or "cash") == "investment"]

    asset_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id).group_by(Asset.asset_type)
    )
    asset_map = {r[0]: float(r[1]) for r in asset_result.all()}

    cum_inc_res = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income",
            Transaction.date < f"{year + 1}-01-01"
        )
    )
    cum_exp_res = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date < f"{year + 1}-01-01"
        )
    )
    cum_inc_val = float(cum_inc_res.scalar() or 0)
    cum_exp_val = float(cum_exp_res.scalar() or 0)

    cash_balance = sum(a.initial_balance for a in cash_accounts) + cum_inc_val - cum_exp_val
    inv_balance = sum(a.initial_balance for a in inv_accounts)
    fixed_assets = asset_map.get("fixed_asset", 0)
    other_assets = asset_map.get("other_asset", 0) + asset_map.get("cash_equivalent", 0)
    inv_assets = asset_map.get("investment", 0)
    liabilities = asset_map.get("liability", 0)
    total_a = cash_balance + inv_balance + fixed_assets + other_assets + inv_assets

    return {
        "period": f"{year}-{month:02d}",
        "assets": {
            "cash": round(cash_balance, 2), "investment_accounts": round(inv_balance, 2),
            "fixed_assets": round(fixed_assets, 2), "other_assets": round(other_assets, 2),
            "investment_assets": round(inv_assets, 2)
        },
        "total_assets": round(total_a, 2),
        "liabilities": round(liabilities, 2),
        "net_worth": round(total_a - liabilities, 2)
    }


async def _build_cf(user_id: str, db: AsyncSession, year: int, month: int) -> dict:
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    txn_result = await db.execute(
        select(Transaction.category_id, Transaction.type, func.sum(Transaction.amount).label("total"))
        .where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.category_id, Transaction.type)
    )
    txn_rows = txn_result.all()

    cat_ids = [r[0] for r in txn_rows if r[0]]
    cat_map = {}
    if cat_ids:
        cats_result = await db.execute(select(Category).where(Category.id.in_(cat_ids)))
        cat_map = {c.id: c for c in cats_result.scalars().all()}

    sections = {"operating": [], "investing": [], "financing": []}
    section_totals = {"operating": 0.0, "investing": 0.0, "financing": 0.0}

    for cat_id, txn_type, total in txn_rows:
        amount = round(float(total), 2)
        if amount == 0:
            continue
        cat = cat_map.get(cat_id)
        cat_name = cat.name if cat else "未知"
        cf = cat.cf_section if cat else ""

        section_key = cf if cf in ("investing", "financing") else "operating"
        signed_amount = amount if txn_type == "income" else -amount
        sections[section_key].append({"name": cat_name, "type": txn_type, "amount": signed_amount})
        section_totals[section_key] += signed_amount

    return {
        "period": f"{year}-{month:02d}",
        "operating": {"items": sections["operating"], "total": round(section_totals["operating"], 2)},
        "investing": {"items": sections["investing"], "total": round(section_totals["investing"], 2)},
        "financing": {"items": sections["financing"], "total": round(section_totals["financing"], 2)},
        "net_cash_flow": round(sum(section_totals.values()), 2)
    }
