from pydantic import BaseModel


class OverviewResponse(BaseModel):
    total_assets: float
    total_income_month: float
    total_expense_month: float
    net_balance: float
    vs_last_month_income: float
    vs_last_month_expense: float
    savings_rate: float
    avg_daily_expense: float
    transaction_count_month: int
    necessary_expense_ratio: float = 0.0
    necessary_expense_ratio_month: float = 0.0
    emergency_reserve_coverage: float = 0.0
    net_worth_growth_rate: float = 0.0
    investment_return_rate: float = 0.0
    investment_return_rate_annualized: float = 0.0
    investment_ratio: float = 0.0


class CategoryStatItem(BaseModel):
    category_id: str
    category_name: str
    category_color: str
    total: float
    count: int


class MonthlyTrendItem(BaseModel):
    month: str
    income: float
    expense: float
    net: float


class TagStatItem(BaseModel):
    tag_id: str
    tag_name: str
    tag_color: str
    total: float
    count: int


class DailySpendingItem(BaseModel):
    date: str
    income: float
    expense: float


class WeekdayPatternItem(BaseModel):
    weekday: int
    label: str
    avg_expense: float
    avg_income: float
    count: int


class TopTransactionItem(BaseModel):
    id: str
    date: str
    type: str
    amount: float
    description: str
    category_name: str
    account_name: str


class NetWorthTrendItem(BaseModel):
    month: str
    net_worth: float
    assets: float
    liabilities: float


class BurnRateItem(BaseModel):
    month: str
    income: float
    expense: float
    burn_rate: float
    savings_rate: float


class CumulativeTrendItem(BaseModel):
    month: str
    cumulative_income: float
    cumulative_expense: float
    cumulative_balance: float


class SavingsRateTrendItem(BaseModel):
    month: str
    savings_rate: float


class NecessaryRatioTrendItem(BaseModel):
    month: str
    necessary_ratio: float


class EmergencyReserveTrendItem(BaseModel):
    month: str
    coverage_months: float


class NetWorthGrowthTrendItem(BaseModel):
    month: str
    growth_rate: float
    yoy_growth_rate: float = 0.0


class CategoryTrendItem(BaseModel):
    month: str
    category_id: str
    category_name: str
    category_color: str
    total: float


class ExpenseVolatilityItem(BaseModel):
    month: str
    total_expense: float
    std_dev: float
    cv: float


class AssetCompositionTrendItem(BaseModel):
    month: str
    cash: float
    investment_accounts: float
    fixed_assets: float
    other_assets: float
    investment_assets: float
    liabilities: float
    total_assets: float
    net_worth: float