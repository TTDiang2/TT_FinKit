from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract, case
from datetime import datetime, timedelta
from calendar import monthrange
from ..database import get_private_db
from ..models.transaction import Transaction
from ..models.category import Category
from ..models.tag import Tag
from ..models.account import Account
from ..models.asset import Asset
from ..models.investment import Investment, open_position_cond
from ..schemas.statistics import (
    OverviewResponse, CategoryStatItem, MonthlyTrendItem, TagStatItem,
    DailySpendingItem, WeekdayPatternItem, TopTransactionItem,
    NetWorthTrendItem, BurnRateItem, CumulativeTrendItem,
    SavingsRateTrendItem, NecessaryRatioTrendItem, EmergencyReserveTrendItem,
    NetWorthGrowthTrendItem, CategoryTrendItem, ExpenseVolatilityItem,
    AssetCompositionTrendItem
)
from ..middleware.auth import get_current_user_id
from typing import List, Optional
import calendar
import math

router = APIRouter(prefix="/api/statistics", tags=["statistics"])

WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_month_range(year: int, month: int):
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year+1}-01-01"
    else:
        end = f"{year}-{month+1:02d}-01"
    return start, end


def resolve_date_range(start_date: Optional[str], end_date: Optional[str], year: Optional[int], month: Optional[int]):
    if start_date and end_date:
        return start_date, end_date
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    return get_month_range(y, m)


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    year: int = Query(default=None),
    month: int = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    last_start, last_end = get_month_range(year if month > 1 else year-1, month-1 if month > 1 else 12)
    three_m_month = month - 2
    three_m_year = year
    while three_m_month <= 0:
        three_m_month += 12
        three_m_year -= 1
    three_months_ago, _ = get_month_range(three_m_year, three_m_month)

    months_in_range: float | None = None
    if start_date and end_date:
        start, end = start_date, end_date
        span_days = max((datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days, 1)
        months_in_range = round(span_days / 30.4375, 1)
    else:
        start, end = get_month_range(year, month)

    inc_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income",
            Transaction.date >= start, Transaction.date < end
        )
    )
    exp_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date >= start, Transaction.date < end
        )
    )
    total_income = float(inc_result.scalar() or 0)
    total_expense = float(exp_result.scalar() or 0)

    inc_last = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income",
            Transaction.date >= last_start, Transaction.date < last_end
        )
    )
    exp_last = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date >= last_start, Transaction.date < last_end
        )
    )
    total_income_last = float(inc_last.scalar() or 0)
    total_expense_last = float(exp_last.scalar() or 0)

    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()
    total_initial = sum(acc.initial_balance for acc in accounts)

    all_inc = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income"
        )
    )
    all_exp = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense"
        )
    )
    total_assets = total_initial + float(all_inc.scalar() or 0) - float(all_exp.scalar() or 0)

    # 投资市值与固定资产/其他资产（Bookkeeping 规范 §2.4：总资产 = 现金 + 投资市值 + 固定资产等）
    inv_result = await db.execute(select(Investment).where(Investment.user_id == user_id, open_position_cond()))
    investments = inv_result.scalars().all()
    total_invested = sum(inv.quantity * inv.purchase_price for inv in investments)
    total_current = sum(inv.quantity * inv.current_price for inv in investments)
    inv_unrealized = total_current - total_invested  # 浮盈（市值-成本），投资账户本金已在账户余额中

    asset_cur_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id)
        .group_by(Asset.asset_type)
    )
    asset_cur_map = {r[0]: float(r[1]) for r in asset_cur_result.all()}
    # 注意：不含 asset_type="investment"（手动投资资产与投资 tab 重复，见 AUDIT B1/D3）
    fixed_plus_other = asset_cur_map.get("fixed_asset", 0) + asset_cur_map.get("other_asset", 0)
    liabilities = asset_cur_map.get("liability", 0)

    # 总资产 = 各账户余额（含转账处理）+ 持仓当前市值 + 固定资产/其他资产 - 负债
    # 使用 get_account_balance 同款公式（initial + income - expense + transfer_in - transfer_out）
    account_balances_sum = 0.0
    for acc in accounts:
        inc_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acc.id, Transaction.type == "income"
            )
        )
        exp_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acc.id, Transaction.type == "expense"
            )
        )
        tout_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acc.id, Transaction.type == "transfer"
            )
        )
        tin_res = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.dest_account_id == acc.id, Transaction.type == "transfer"
            )
        )
        acc_income = float(inc_res.scalar() or 0)
        acc_expense = float(exp_res.scalar() or 0)
        acc_transfer_out = float(tout_res.scalar() or 0)
        acc_transfer_in = float(tin_res.scalar() or 0)
        account_balances_sum += acc.initial_balance + acc_income - acc_expense + acc_transfer_in - acc_transfer_out

    total_assets = account_balances_sum + total_current + fixed_plus_other - liabilities

    vs_income = ((total_income - total_income_last) / total_income_last * 100) if total_income_last else 0
    vs_expense = ((total_expense - total_expense_last) / total_expense_last * 100) if total_expense_last else 0

    days_in_month = monthrange(year, month)[1]
    days_in_window = span_days if months_in_range is not None else days_in_month
    savings_rate = ((total_income - total_expense) / total_income * 100) if total_income > 0 else 0

    txn_count_result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end
        )
    )

    necessary_exp_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date >= three_months_ago, Transaction.date < end,
            Category.is_necessary == True
        )
    )
    necessary_expense = float(necessary_exp_result.scalar() or 0)
    total_3m_expense_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date >= three_months_ago, Transaction.date < end
        )
    )
    total_3m_expense = float(total_3m_expense_result.scalar() or 0)
    necessary_ratio = (necessary_expense / total_3m_expense * 100) if total_3m_expense > 0 else 0

    necessary_exp_month_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date >= start, Transaction.date < end,
            Category.is_necessary == True
        )
    )
    necessary_expense_month = float(necessary_exp_month_result.scalar() or 0)
    necessary_ratio_month = (necessary_expense_month / total_expense * 100) if total_expense > 0 else 0

    avg_3m_expense = 0.0
    for mi in range(1, 4):
        pm_year = year
        pm_month = month - mi
        while pm_month <= 0:
            pm_month += 12
            pm_year -= 1
        pm_start, pm_end = get_month_range(pm_year, pm_month)
        pm_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= pm_start, Transaction.date < pm_end
            )
        )
        avg_3m_expense += float(pm_exp.scalar() or 0)
    avg_3m_expense = avg_3m_expense / 3.0
    emergency_coverage = (total_assets / avg_3m_expense) if avg_3m_expense > 0 else 0

    prev_nw_start, prev_nw_end = get_month_range(year if month > 2 else year - 1, month - 2 if month > 2 else month + 10)
    prev_cum_inc = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income",
            Transaction.date < prev_nw_end
        )
    )
    prev_cum_exp = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date < prev_nw_end
        )
    )
    prev_cash = total_initial + float(prev_cum_inc.scalar() or 0) - float(prev_cum_exp.scalar() or 0)
    prev_asset_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id)
        .group_by(Asset.asset_type)
    )
    prev_asset_map = {r[0]: float(r[1]) for r in prev_asset_result.all()}
    # 与当月口径一致：fixed_asset + other_asset（不含手动 investment 资产）
    prev_fixed_plus = prev_asset_map.get("fixed_asset", 0) + prev_asset_map.get("other_asset", 0)
    prev_liabilities = prev_asset_map.get("liability", 0)
    prev_net_worth = (prev_cash + prev_fixed_plus) - prev_liabilities
    cur_net_worth = total_assets - prev_liabilities
    net_worth_growth = ((cur_net_worth - prev_net_worth) / prev_net_worth * 100) if prev_net_worth != 0 else 0

    # investments 已在上面 total_assets 计算处加载（investments/total_invested/total_current）
    # 改用 XIRR 年化收益率（与投资 tab 同款公式）
    from ..services.investment_stats import compute_portfolio_overview
    portfolio_overview = await compute_portfolio_overview(db, user_id)
    xirr_annualized = portfolio_overview.xirr_annualized if portfolio_overview.xirr_annualized is not None else 0.0
    annualized_return = round(xirr_annualized * 100, 2)
    # 投资收益率（simple return）
    inv_return = ((total_current - total_invested) / total_invested * 100) if total_invested > 0 else 0
    # 投资比率：使用组合当前市值 / 总资产
    investment_ratio = (portfolio_overview.current_market_value / total_assets * 100) if total_assets > 0 else 0

    return OverviewResponse(
        total_assets=total_assets,
        total_income_month=total_income,
        total_expense_month=total_expense,
        net_balance=total_income - total_expense,
        vs_last_month_income=round(vs_income, 1),
        vs_last_month_expense=round(vs_expense, 1),
        savings_rate=round(savings_rate, 1),
        avg_daily_expense=round(total_expense / days_in_window, 2) if days_in_window else 0,
        transaction_count_month=txn_count_result.scalar() or 0,
        necessary_expense_ratio=round(necessary_ratio, 1),
        necessary_expense_ratio_month=round(necessary_ratio_month, 1),
        emergency_reserve_coverage=round(emergency_coverage, 1),
        net_worth_growth_rate=round(net_worth_growth, 2),
        investment_return_rate=round(inv_return, 2),
        investment_return_rate_annualized=round(annualized_return, 2),
        investment_ratio=round(investment_ratio, 1),
        months_in_range=months_in_range,
    )


@router.get("/by-category", response_model=List[CategoryStatItem])
async def get_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    year: int | None = None,
    month: int | None = None,
    type_filter: str = "expense",
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    start, end = resolve_date_range(start_date, end_date, year, month)

    result = await db.execute(
        select(
            Transaction.category_id,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
            func.coalesce(
                func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0.0)),
                0.0,
            ).label("positive_total"),
            func.coalesce(
                func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0.0)),
                0.0,
            ).label("negative_total"),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.type == type_filter,
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.category_id.isnot(None)
        )
        .group_by(Transaction.category_id)
        .order_by(func.sum(Transaction.amount).desc())
    )
    rows = result.all()

    cat_ids = [r[0] for r in rows]
    if not cat_ids:
        return []
    cats_result = await db.execute(select(Category).where(Category.id.in_(cat_ids)))
    cat_map = {c.id: (c.name, c.color) for c in cats_result.scalars().all()}

    return [CategoryStatItem(
        category_id=r[0], category_name=cat_map.get(r[0], ("未知", "#9B9B9B"))[0],
        category_color=cat_map.get(r[0], ("未知", "#9B9B9B"))[1],
        total=float(r[1]), count=int(r[2]),
        positive_total=float(r[3] or 0.0),
        negative_total=float(r[4] or 0.0),
    ) for r in rows]


@router.get("/monthly-trend", response_model=List[MonthlyTrendItem])
async def get_monthly_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    results = []
    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        inc_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date >= start, Transaction.date < end
            )
        )
        exp_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end
            )
        )
        income = float(inc_result.scalar() or 0)
        expense = float(exp_result.scalar() or 0)
        results.append(MonthlyTrendItem(
            month=f"{m_year}-{m_month:02d}", income=income, expense=expense, net=income - expense
        ))
    return results


@router.get("/by-tag", response_model=List[TagStatItem])
async def get_by_tag(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    year: int | None = None,
    month: int | None = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    start, end = resolve_date_range(start_date, end_date, year, month)

    result = await db.execute(
        select(Transaction.tag_ids)
        .where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)
    )
    txns = result.scalars().all()

    tag_totals: dict = {}
    for txn in txns:
        if txn and isinstance(txn, list):
            for tag_id in txn:
                tag_totals[tag_id] = tag_totals.get(tag_id, 0) + 1

    tag_ids = list(tag_totals.keys())
    if not tag_ids:
        return []
    tags_result = await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
    tag_map = {t.id: (t.name, t.color) for t in tags_result.scalars().all()}

    return [TagStatItem(
        tag_id=tid, tag_name=tag_map.get(tid, ("未知", "#9B9B9B"))[0],
        tag_color=tag_map.get(tid, ("未知", "#9B9B9B"))[1],
        total=float(count), count=count
    ) for tid, count in sorted(tag_totals.items(), key=lambda x: -x[1])]


@router.get("/daily-spending", response_model=List[DailySpendingItem])
async def get_daily_spending(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    year: int | None = None,
    month: int | None = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    start, end = resolve_date_range(start_date, end_date, year, month)

    # 按行查询后在 Python 侧聚合：负支出（退款冲销）不计入每日支出
    result = await db.execute(
        select(Transaction.date, Transaction.type, Transaction.amount)
        .where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)
        .order_by(Transaction.date)
    )
    rows = result.all()

    daily: dict = {}
    for date, txn_type, amount in rows:
        if date not in daily:
            daily[date] = {"date": date, "income": 0.0, "expense": 0.0}
        if txn_type == "income":
            daily[date]["income"] += max(0.0, float(amount))
        elif txn_type == "expense":
            daily[date]["expense"] += max(0.0, float(amount))  # 负支出（退款）不计入

    return [DailySpendingItem(**v) for v in sorted(daily.values(), key=lambda x: x["date"])]


@router.get("/weekday-pattern", response_model=List[WeekdayPatternItem])
async def get_weekday_pattern(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    year: int | None = None,
    month: int | None = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    start, end = resolve_date_range(start_date, end_date, year, month)

    result = await db.execute(
        select(
            extract("dow", Transaction.date).label("dow"),
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("cnt")
        )
        .where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)
        .group_by("dow", Transaction.type)
    )
    rows = result.all()

    # SQLite dow: 0=Sunday -> remap to Mon=0 .. Sun=6
    pattern: dict = {}
    for i in range(7):
        pattern[i] = {"weekday": i, "label": WEEKDAY_LABELS[i], "avg_expense": 0.0, "avg_income": 0.0, "count": 0}

    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days or 1
    weeks = max(total_days / 7, 1)

    for dow, txn_type, total, cnt in rows:
        dow = int(dow)
        # Convert Sunday=0 to Monday-based: Mon=0,Tue=1,...,Sun=6
        mapped = (dow - 1) % 7
        if mapped not in pattern:
            continue
        if txn_type == "expense":
            pattern[mapped]["avg_expense"] = round(float(total) / weeks, 2)
        elif txn_type == "income":
            pattern[mapped]["avg_income"] = round(float(total) / weeks, 2)
        pattern[mapped]["count"] += int(cnt)

    return [WeekdayPatternItem(**v) for v in pattern.values()]


@router.get("/top-expenses", response_model=List[TopTransactionItem])
async def get_top_expenses(
    limit: int = Query(default=5, ge=1, le=20),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    year: int | None = None,
    month: int | None = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    start, end = resolve_date_range(start_date, end_date, year, month)

    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.type == "expense", Transaction.date >= start, Transaction.date < end)
        .order_by(Transaction.amount.desc())
        .limit(limit)
    )
    txns = result.scalars().all()
    if not txns:
        return []

    acc_ids = set(t.account_id for t in txns if t.account_id)
    cat_ids = set(t.category_id for t in txns if t.category_id)

    acc_result = await db.execute(select(Account).where(Account.id.in_(acc_ids)))
    acc_map = {a.id: a.name for a in acc_result.scalars().all()}

    cat_result = await db.execute(select(Category).where(Category.id.in_(cat_ids)))
    cat_map = {c.id: c.name for c in cat_result.scalars().all()}

    return [TopTransactionItem(
        id=t.id, date=t.date, type=t.type, amount=t.amount,
        description=t.description or "", category_name=cat_map.get(t.category_id, ""),
        account_name=acc_map.get(t.account_id, "")
    ) for t in txns]


@router.get("/net-worth-trend", response_model=List[NetWorthTrendItem])
async def get_net_worth_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()

    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()
    total_initial = sum(acc.initial_balance for acc in accounts)

    asset_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id)
        .group_by(Asset.asset_type)
    )
    asset_type_map = {r[0]: float(r[1]) for r in asset_result.all()}
    fixed_plus_other = asset_type_map.get("fixed_asset", 0) + asset_type_map.get("other_asset", 0) + asset_type_map.get("investment", 0)
    total_liabilities = asset_type_map.get("liability", 0)

    results = []
    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        if m_month == 12:
            period_end = f"{m_year + 1}-01-01"
        else:
            period_end = f"{m_year}-{m_month + 1:02d}-01"

        cum_inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date < period_end
            )
        )
        cum_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date < period_end
            )
        )
        cash = total_initial + float(cum_inc.scalar() or 0) - float(cum_exp.scalar() or 0)
        total_assets = cash + fixed_plus_other
        net_worth = total_assets - total_liabilities

        results.append(NetWorthTrendItem(
            month=f"{m_year}-{m_month:02d}",
            net_worth=round(net_worth, 2),
            assets=round(total_assets, 2),
            liabilities=round(total_liabilities, 2)
        ))
    return results


@router.get("/burn-rate", response_model=List[BurnRateItem])
async def get_burn_rate(
    months: int = Query(default=6, ge=1, le=12),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    results = []

    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        inc_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date >= start, Transaction.date < end
            )
        )
        exp_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end
            )
        )
        income = float(inc_result.scalar() or 0)
        expense = float(exp_result.scalar() or 0)
        burn = expense - income
        rate = ((income - expense) / income * 100) if income > 0 else 0

        results.append(BurnRateItem(
            month=f"{m_year}-{m_month:02d}",
            income=round(income, 2),
            expense=round(expense, 2),
            burn_rate=round(burn, 2),
            savings_rate=round(rate, 1)
        ))
    return results


@router.get("/cumulative-trend", response_model=List[CumulativeTrendItem])
async def get_cumulative_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    results = []
    cum_income = 0.0
    cum_expense = 0.0

    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        inc_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date >= start, Transaction.date < end
            )
        )
        exp_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end
            )
        )
        cum_income += float(inc_result.scalar() or 0)
        cum_expense += float(exp_result.scalar() or 0)

        results.append(CumulativeTrendItem(
            month=f"{m_year}-{m_month:02d}",
            cumulative_income=round(cum_income, 2),
            cumulative_expense=round(cum_expense, 2),
            cumulative_balance=round(cum_income - cum_expense, 2)
        ))
    return results


@router.get("/savings-rate-trend", response_model=List[SavingsRateTrendItem])
async def get_savings_rate_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    results = []

    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        inc_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date >= start, Transaction.date < end
            )
        )
        exp_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end
            )
        )
        income = float(inc_result.scalar() or 0)
        expense = float(exp_result.scalar() or 0)
        rate = ((income - expense) / income * 100) if income > 0 else 0

        results.append(SavingsRateTrendItem(
            month=f"{m_year}-{m_month:02d}",
            savings_rate=round(rate, 1)
        ))
    return results


@router.get("/necessary-ratio-trend", response_model=List[NecessaryRatioTrendItem])
async def get_necessary_ratio_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    results = []

    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        total_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end
            )
        )
        necessary_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .select_from(Transaction)
            .join(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end,
                Category.is_necessary == True
            )
        )
        total = float(total_exp.scalar() or 0)
        necessary = float(necessary_exp.scalar() or 0)
        ratio = (necessary / total * 100) if total > 0 else 0

        results.append(NecessaryRatioTrendItem(
            month=f"{m_year}-{m_month:02d}",
            necessary_ratio=round(ratio, 1)
        ))
    return results


@router.get("/emergency-reserve-trend", response_model=List[EmergencyReserveTrendItem])
async def get_emergency_reserve_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False, Account.account_type == "cash"))
    accounts = acc_result.scalars().all()
    total_initial = sum(acc.initial_balance for acc in accounts)

    results = []
    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        if m_month == 12:
            period_end = f"{m_year + 1}-01-01"
        else:
            period_end = f"{m_year}-{m_month + 1:02d}-01"

        cum_inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date < period_end
            )
        )
        cum_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date < period_end
            )
        )
        cash = total_initial + float(cum_inc.scalar() or 0) - float(cum_exp.scalar() or 0)

        avg_3m_exp = 0.0
        for mi in range(1, 4):
            pm_year = m_year
            pm_month = m_month - mi
            while pm_month <= 0:
                pm_month += 12
                pm_year -= 1
            pm_start, pm_end = get_month_range(pm_year, pm_month)
            pm_exp = await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id, Transaction.type == "expense",
                    Transaction.date >= pm_start, Transaction.date < pm_end
                )
            )
            avg_3m_exp += float(pm_exp.scalar() or 0)
        avg_3m_exp /= 3.0

        coverage = (cash / avg_3m_exp) if avg_3m_exp > 0 else 0
        results.append(EmergencyReserveTrendItem(
            month=f"{m_year}-{m_month:02d}",
            coverage_months=round(coverage, 1)
        ))
    return results


@router.get("/net-worth-growth-trend", response_model=List[NetWorthGrowthTrendItem])
async def get_net_worth_growth_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()
    total_initial = sum(acc.initial_balance for acc in accounts)

    asset_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id)
        .group_by(Asset.asset_type)
    )
    asset_type_map = {r[0]: float(r[1]) for r in asset_result.all()}
    fixed_plus = asset_type_map.get("fixed_asset", 0) + asset_type_map.get("other_asset", 0) + asset_type_map.get("investment", 0)
    total_liabilities = asset_type_map.get("liability", 0)

    net_worths = []
    for i in range(months, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        if m_month == 12:
            period_end = f"{m_year + 1}-01-01"
        else:
            period_end = f"{m_year}-{m_month + 1:02d}-01"

        cum_inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date < period_end
            )
        )
        cum_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date < period_end
            )
        )
        cash = total_initial + float(cum_inc.scalar() or 0) - float(cum_exp.scalar() or 0)
        nw = (cash + fixed_plus) - total_liabilities
        net_worths.append((f"{m_year}-{m_month:02d}", nw))

    results = []
    for idx in range(1, len(net_worths)):
        prev_nw = net_worths[idx - 1][1]
        cur_nw = net_worths[idx][1]
        mom_growth = ((cur_nw - prev_nw) / abs(prev_nw) * 100) if prev_nw != 0 else 0

        cur_year, cur_month = net_worths[idx][0].split("-")
        yoy_year = int(cur_year) - 1
        yoy_month_str = f"{yoy_year}-{cur_month}"
        yoy_growth = 0.0
        for m_label, m_nw in net_worths:
            if m_label == yoy_month_str:
                yoy_growth = ((cur_nw - m_nw) / abs(m_nw) * 100) if m_nw != 0 else 0
                break

        results.append(NetWorthGrowthTrendItem(
            month=net_worths[idx][0],
            growth_rate=round(mom_growth, 2),
            yoy_growth_rate=round(yoy_growth, 2)
        ))
    return results


@router.get("/category-trend", response_model=List[CategoryTrendItem])
async def get_category_trend(
    type_filter: str = Query(default="expense"),
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    all_results = []

    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        result = await db.execute(
            select(Transaction.category_id, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.user_id == user_id, Transaction.type == type_filter,
                Transaction.date >= start, Transaction.date < end,
                Transaction.category_id.isnot(None)
            )
            .group_by(Transaction.category_id)
        )
        rows = result.all()
        if not rows:
            continue

        cat_ids = [r[0] for r in rows]
        cats_result = await db.execute(select(Category).where(Category.id.in_(cat_ids)))
        cat_map = {c.id: (c.name, c.color) for c in cats_result.scalars().all()}

        for cat_id, total in rows:
            name, color = cat_map.get(cat_id, ("未知", "#9B9B9B"))
            all_results.append(CategoryTrendItem(
                month=f"{m_year}-{m_month:02d}",
                category_id=cat_id,
                category_name=name,
                category_color=color,
                total=round(float(total), 2)
            ))
    return all_results


@router.get("/expense-volatility", response_model=List[ExpenseVolatilityItem])
async def get_expense_volatility(
    months: int = Query(default=12, ge=3, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()
    monthly_expenses = []

    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        start, end = get_month_range(m_year, m_month)

        exp_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date >= start, Transaction.date < end
            )
        )
        expense = float(exp_result.scalar() or 0)
        monthly_expenses.append((f"{m_year}-{m_month:02d}", expense))

    results = []
    window = min(3, len(monthly_expenses))
    for idx in range(len(monthly_expenses)):
        start_idx = max(0, idx - window + 1)
        window_vals = [monthly_expenses[j][1] for j in range(start_idx, idx + 1)]
        avg = sum(window_vals) / len(window_vals)
        variance = sum((v - avg) ** 2 for v in window_vals) / len(window_vals)
        std_dev = math.sqrt(variance)
        cv = (std_dev / avg * 100) if avg > 0 else 0

        results.append(ExpenseVolatilityItem(
            month=monthly_expenses[idx][0],
            total_expense=round(monthly_expenses[idx][1], 2),
            std_dev=round(std_dev, 2),
            cv=round(cv, 1)
        ))
    return results


@router.get("/asset-composition-trend", response_model=List[AssetCompositionTrendItem])
async def get_asset_composition_trend(
    months: int = Query(default=12, ge=1, le=60),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_private_db)
):
    now = datetime.now()

    # Get accounts grouped by type
    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()
    cash_accounts = [a for a in accounts if (a.account_type or 'cash') == 'cash']
    inv_accounts = [a for a in accounts if (a.account_type or 'cash') == 'investment']
    total_cash_initial = sum(a.initial_balance for a in cash_accounts)
    total_inv_initial = sum(a.initial_balance for a in inv_accounts)

    # Get manual assets grouped by type (constant values)
    asset_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id)
        .group_by(Asset.asset_type)
    )
    asset_type_map = {r[0]: float(r[1]) for r in asset_result.all()}
    fixed_assets = asset_type_map.get("fixed_asset", 0)
    other_assets = asset_type_map.get("other_asset", 0) + asset_type_map.get("cash_equivalent", 0)
    investment_assets = asset_type_map.get("investment", 0)
    total_liabilities = asset_type_map.get("liability", 0)

    results = []
    for i in range(months - 1, -1, -1):
        m_year = now.year
        m_month = now.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        if m_month == 12:
            period_end = f"{m_year + 1}-01-01"
        else:
            period_end = f"{m_year}-{m_month + 1:02d}-01"

        # Cash from transactions on cash accounts
        cash_acc_ids = [a.id for a in cash_accounts]
        inv_acc_ids = [a.id for a in inv_accounts]
        if cash_acc_ids:
            cum_cash_inc = await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id, Transaction.type == "income",
                    Transaction.account_id.in_(cash_acc_ids), Transaction.date < period_end
                )
            )
            cum_cash_exp = await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id, Transaction.type == "expense",
                    Transaction.account_id.in_(cash_acc_ids), Transaction.date < period_end
                )
            )
            cash = total_cash_initial + float(cum_cash_inc.scalar() or 0) - float(cum_cash_exp.scalar() or 0)
        else:
            cash = 0

        if inv_acc_ids:
            cum_inv_inc = await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id, Transaction.type == "income",
                    Transaction.account_id.in_(inv_acc_ids), Transaction.date < period_end
                )
            )
            cum_inv_exp = await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user_id, Transaction.type == "expense",
                    Transaction.account_id.in_(inv_acc_ids), Transaction.date < period_end
                )
            )
            inv_acc_balance = total_inv_initial + float(cum_inv_inc.scalar() or 0) - float(cum_inv_exp.scalar() or 0)
        else:
            inv_acc_balance = 0

        total_assets = cash + inv_acc_balance + fixed_assets + other_assets + investment_assets
        net_worth = total_assets - total_liabilities

        results.append(AssetCompositionTrendItem(
            month=f"{m_year}-{m_month:02d}",
            cash=round(cash, 2),
            investment_accounts=round(inv_acc_balance, 2),
            fixed_assets=round(fixed_assets, 2),
            other_assets=round(other_assets, 2),
            investment_assets=round(investment_assets, 2),
            liabilities=round(total_liabilities, 2),
            total_assets=round(total_assets, 2),
            net_worth=round(net_worth, 2)
        ))
    return results