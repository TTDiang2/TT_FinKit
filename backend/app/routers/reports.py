from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from calendar import monthrange
from ..database import get_db
from ..models.report_archive import ReportArchive
from ..models.transaction import Transaction
from ..models.account import Account
from ..models.category import Category
from ..models.asset import Asset
from ..models.investment import Investment
from ..schemas.report import ReportArchiveCreate, ReportArchiveResponse
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/reports", tags=["reports"])


def get_period_range(period_type: str, year: int, month: int = 1, quarter: int = 1):
    if period_type == "annual":
        return f"{year}-01-01", f"{year + 1}-01-01"
    elif period_type == "quarterly":
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        if end_month == 12:
            return f"{year}-{start_month:02d}-01", f"{year + 1}-01-01"
        else:
            return f"{year}-{start_month:02d}-01", f"{year}-{end_month + 1:02d}-01"
    else:
        if month == 12:
            return f"{year}-{month:02d}-01", f"{year + 1}-01-01"
        else:
            return f"{year}-{month:02d}-01", f"{year}-{month + 1:02d}-01"


def get_period_label(period_type: str, year: int, month: int = 1, quarter: int = 1) -> str:
    if period_type == "annual":
        return f"{year}"
    elif period_type == "quarterly":
        return f"{year}-Q{quarter}"
    else:
        return f"{year}-{month:02d}"


@router.get("/pl")
async def get_profit_loss(
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    period_type: str = Query(default="monthly", regex="^(monthly|quarterly|annual)$"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    quarter = quarter or (month - 1) // 3 + 1

    start, end = get_period_range(period_type, year, month, quarter)
    period_label = get_period_label(period_type, year, month, quarter)

    txn_result = await db.execute(
        select(Transaction.category_id, Transaction.type, func.sum(Transaction.amount).label("total"))
        .where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.category_id, Transaction.type)
    )
    txn_rows = txn_result.all()

    cat_ids = [r[0] for r in txn_rows if r[0]]
    cats_result = await db.execute(select(Category).where(Category.id.in_(cat_ids)))
    cat_map = {c.id: c for c in cats_result.scalars().all()}

    main_income = []
    other_income = []
    main_cost = []
    other_cost = []
    total_main_income = 0.0
    total_other_income = 0.0
    total_main_cost = 0.0
    total_other_cost = 0.0

    for cat_id, txn_type, total in txn_rows:
        amount = round(float(total), 2)
        if amount == 0:
            continue
        cat = cat_map.get(cat_id)
        cat_name = cat.name if cat else "未知"

        if txn_type == "income":
            pl_section = cat.pl_section if cat else ""
            if pl_section == "exclude_income":
                continue
            elif pl_section == "other_income":
                other_income.append({"name": cat_name, "total": amount})
                total_other_income += amount
            else:
                main_income.append({"name": cat_name, "total": amount})
                total_main_income += amount
        elif txn_type == "expense":
            pl_section = cat.pl_section if cat else ""
            if pl_section == "exclude_expense":
                continue
            elif pl_section == "other_cost":
                other_cost.append({"name": cat_name, "total": amount})
                total_other_cost += amount
            else:
                main_cost.append({"name": cat_name, "total": amount})
                total_main_cost += amount

    total_income = total_main_income + total_other_income
    total_expense = total_main_cost + total_other_cost
    gross_profit = total_main_income - total_main_cost
    gross_margin = (gross_profit / total_main_income * 100) if total_main_income > 0 else 0
    net_income = total_income - total_expense
    net_margin = (net_income / total_income * 100) if total_income > 0 else 0

    return {
        "main_income": main_income,
        "other_income": other_income,
        "main_cost": main_cost,
        "other_cost": other_cost,
        "total_main_income": round(total_main_income, 2),
        "total_other_income": round(total_other_income, 2),
        "total_income": round(total_income, 2),
        "total_main_cost": round(total_main_cost, 2),
        "total_other_cost": round(total_other_cost, 2),
        "total_expense": round(total_expense, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin": round(gross_margin, 1),
        "net_income": round(net_income, 2),
        "net_margin": round(net_margin, 1),
        "period": period_label
    }


@router.get("/bs")
async def get_balance_sheet(
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    period_type: str = Query(default="monthly", regex="^(monthly|quarterly|annual)$"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    quarter = quarter or (month - 1) // 3 + 1

    _, end = get_period_range(period_type, year, month, quarter)
    period_label = get_period_label(period_type, year, month, quarter)

    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()

    cash_accounts = [a for a in accounts if a.account_type != "investment" and a.account_type != "custodial"]
    investment_accounts = [a for a in accounts if a.account_type == "investment"]
    custodial_accounts = [a for a in accounts if a.account_type == "custodial"]

    total_initial = sum(acc.initial_balance for acc in accounts)
    cum_inc = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income", Transaction.date < end
        )
    )
    cum_exp = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense", Transaction.date < end
        )
    )
    cash_balance = total_initial + float(cum_inc.scalar() or 0) - float(cum_exp.scalar() or 0)

    inv_result = await db.execute(select(Investment).where(Investment.user_id == user_id, Investment.sell_date == None))
    investments = inv_result.scalars().all()
    total_inv_current = sum(inv.quantity * inv.current_price for inv in investments)

    inv_account_initial = sum(a.initial_balance for a in investment_accounts)
    inv_acct_balance = inv_account_initial
    if investment_accounts:
        inv_acct_inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date < end,
                Transaction.account_id.in_([a.id for a in investment_accounts])
            )
        )
        inv_acct_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date < end,
                Transaction.account_id.in_([a.id for a in investment_accounts])
            )
        )
        inv_acct_balance = inv_account_initial + float(inv_acct_inc.scalar() or 0) - float(inv_acct_exp.scalar() or 0)
    else:
        inv_acct_balance = 0.0

    custodial_initial = sum(a.initial_balance for a in custodial_accounts)
    custodial_balance = custodial_initial
    if custodial_accounts:
        cust_inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "income",
                Transaction.date < end,
                Transaction.account_id.in_([a.id for a in custodial_accounts])
            )
        )
        cust_exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id, Transaction.type == "expense",
                Transaction.date < end,
                Transaction.account_id.in_([a.id for a in custodial_accounts])
            )
        )
        custodial_balance = custodial_initial + float(cust_inc.scalar() or 0) - float(cust_exp.scalar() or 0)

    asset_result = await db.execute(
        select(Asset.asset_type, func.sum(Asset.value).label("total"))
        .where(Asset.user_id == user_id).group_by(Asset.asset_type)
    )
    asset_type_map = {r[0]: float(r[1]) for r in asset_result.all()}
    fixed_assets = asset_type_map.get("fixed_asset", 0)
    other_assets = asset_type_map.get("other_asset", 0)
    manual_inv_assets = asset_type_map.get("investment", 0)
    liabilities = asset_type_map.get("liability", 0)

    liquid_assets = cash_balance
    trading_securities = total_inv_current + inv_acct_balance + manual_inv_assets
    total_investment_assets = trading_securities

    asset_items = []
    if round(liquid_assets, 2) != 0:
        asset_items.append({"name": "货币资金（流动资产）", "total": round(liquid_assets, 2)})
    if round(total_investment_assets, 2) != 0:
        asset_items.append({"name": "交易性金融资产", "total": round(total_investment_assets, 2)})
    if round(fixed_assets, 2) != 0:
        asset_items.append({"name": "固定资产", "total": round(fixed_assets, 2)})
    if round(custodial_balance, 2) != 0:
        asset_items.append({"name": "代管资产", "total": round(custodial_balance, 2)})
    if round(other_assets, 2) != 0:
        asset_items.append({"name": "其他资产", "total": round(other_assets, 2)})

    total_assets_value = liquid_assets + total_investment_assets + fixed_assets + custodial_balance + other_assets
    net_worth = total_assets_value - liabilities

    liability_items = []
    if round(liabilities, 2) != 0:
        liability_items.append({"name": "负债", "total": round(liabilities, 2)})

    equity_items = [{"name": "权益（净资产）", "total": round(net_worth, 2)}]

    return {
        "assets": asset_items,
        "liabilities": liability_items,
        "equity": equity_items,
        "total_assets": round(total_assets_value, 2),
        "total_liabilities": round(liabilities, 2),
        "total_liabilities_equity": round(liabilities + net_worth, 2),
        "net_worth": round(net_worth, 2),
        "period": period_label
    }


@router.get("/cf")
async def get_cash_flow(
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    period_type: str = Query(default="monthly", regex="^(monthly|quarterly|annual)$"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    quarter = quarter or (month - 1) // 3 + 1

    start, end = get_period_range(period_type, year, month, quarter)
    period_label = get_period_label(period_type, year, month, quarter)

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

    operating_items = []
    investing_items = []
    financing_items = []
    operating_net = 0.0
    investing_net = 0.0
    financing_net = 0.0

    for cat_id, txn_type, total in txn_rows:
        cat = cat_map.get(cat_id)
        cat_name = cat.name if cat else "其他"
        cf_section = cat.cf_section if cat else ""
        amount = float(total)
        signed_amount = amount if txn_type == "income" else -amount

        if cf_section == "financing":
            financing_items.append({"name": cat_name, "total": round(signed_amount, 2)})
            financing_net += signed_amount
        elif cf_section == "investing":
            investing_items.append({"name": cat_name, "total": round(signed_amount, 2)})
            investing_net += signed_amount
        else:
            operating_items.append({"name": cat_name, "total": round(signed_amount, 2)})
            operating_net += signed_amount

    operating_items = [i for i in operating_items if i["total"] != 0]
    investing_items = [i for i in investing_items if i["total"] != 0]
    financing_items = [i for i in financing_items if i["total"] != 0]

    net_change = operating_net + investing_net + financing_net

    acc_result = await db.execute(select(Account).where(Account.user_id == user_id, Account.hidden == False))
    accounts = acc_result.scalars().all()
    total_initial = sum(acc.initial_balance for acc in accounts)

    cum_inc_before = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "income",
            Transaction.date < start
        )
    )
    cum_exp_before = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.type == "expense",
            Transaction.date < start
        )
    )
    beginning_cash = total_initial + float(cum_inc_before.scalar() or 0) - float(cum_exp_before.scalar() or 0)

    return {
        "operating": operating_items,
        "operating_net": round(operating_net, 2),
        "investing": investing_items,
        "investing_net": round(investing_net, 2),
        "financing": financing_items,
        "financing_net": round(financing_net, 2),
        "net_change": round(net_change, 2),
        "beginning_cash": round(beginning_cash, 2),
        "ending_cash": round(beginning_cash + net_change, 2),
        "period": period_label
    }


@router.get("/archives", response_model=List[ReportArchiveResponse])
async def get_archives(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReportArchive).where(ReportArchive.user_id == user_id).order_by(ReportArchive.generated_at.desc())
    )
    archives = result.scalars().all()
    return [ReportArchiveResponse(
        id=a.id, user_id=a.user_id, report_type=a.report_type,
        period_start=a.period_start, period_end=a.period_end, generated_at=str(a.generated_at)
    ) for a in archives]


@router.post("/archives", response_model=ReportArchiveResponse)
async def create_archive(req: ReportArchiveCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    archive = ReportArchive(user_id=user_id, **req.model_dump())
    db.add(archive)
    await db.commit()
    await db.refresh(archive)
    return ReportArchiveResponse(
        id=archive.id, user_id=archive.user_id, report_type=archive.report_type,
        period_start=archive.period_start, period_end=archive.period_end, generated_at=str(archive.generated_at)
    )


@router.get("/archives/{archive_id}")
async def get_archive(archive_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReportArchive).where(ReportArchive.id == archive_id, ReportArchive.user_id == user_id)
    )
    archive = result.scalar_one_or_none()
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    return {"id": archive.id, "report_type": archive.report_type, "content": archive.content, "period_start": archive.period_start, "period_end": archive.period_end}


@router.delete("/archives/{archive_id}")
async def delete_archive(archive_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReportArchive).where(ReportArchive.id == archive_id, ReportArchive.user_id == user_id)
    )
    archive = result.scalar_one_or_none()
    if not archive:
        raise HTTPException(status_code=404, detail="Archive not found")
    await db.delete(archive)
    await db.commit()
    return {"message": "Archive deleted"}