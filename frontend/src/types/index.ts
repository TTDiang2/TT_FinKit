export interface User { id: string; email: string; name: string; created_at: string }
export interface Account { id: string; user_id: string; name: string; currency: string; initial_balance: number; hidden: boolean; sort_order: number; current_balance: number; account_type: string; bank_statement_mode?: string; created_at: string; updated_at: string }
export interface Category { id: string; user_id: string; type: 'income' | 'expense'; name: string; color: string; icon: string; sort_order: number; is_necessary: boolean; pl_section: string; cf_section: string; created_at: string; updated_at: string }
export interface Tag { id: string; user_id: string; name: string; color: string; created_at: string }
export interface Transaction { id: string; user_id: string; type: 'income' | 'expense' | 'transfer'; date: string; amount: number; account_id: string; dest_account_id?: string; category_id?: string; tag_ids: string[]; description: string; remark: string; location?: string; created_at: string; updated_at: string; account_name?: string; category_name?: string; category_color?: string }
export interface Overview { total_assets: number; total_income_month: number; total_expense_month: number; net_balance: number; vs_last_month_income: number; vs_last_month_expense: number; savings_rate: number; avg_daily_expense: number; transaction_count_month: number; necessary_expense_ratio: number; emergency_reserve_coverage: number; net_worth_growth_rate: number; investment_return_rate: number; investment_return_rate_annualized: number; investment_ratio: number }
export interface CategoryStat { category_id: string; category_name: string; category_color: string; total: number; count: number }
export interface MonthlyTrend { month: string; income: number; expense: number; net: number }
export interface UserSettings {
  language: string; currency_symbol: string; date_format: string; timezone: string; sidebar_expanded: boolean;
  ai_search_backend?: string; ai_search_api_key?: string; ai_investment_preset_id?: string | null;
  ifind_username?: string;        // 同花顺 iFinD 账号
  ifind_password?: string;        // 仅写入用（后端不回传明文）
  has_ifind_password?: boolean;   // 是否已配置密码（密码本身不回传）
}
export interface ReportArchive { id: string; user_id: string; report_type: string; period_start: string; period_end: string; generated_at: string; content?: string }
export interface DailySpending { date: string; income: number; expense: number }
export interface WeekdayPattern { weekday: number; label: string; avg_expense: number; avg_income: number; count: number }
export interface TopTransaction { id: string; date: string; type: string; amount: number; description: string; category_name: string; account_name: string }

export interface Asset {
  id: string; user_id: string; name: string;
  asset_type: 'fixed_asset' | 'cash_equivalent' | 'investment' | 'other_asset' | 'liability';
  value: number; description: string; acquisition_date: string; notes: string;
  created_at: string; updated_at: string;
}

export interface Investment {
  id: string; user_id: string; name: string;
  investment_type: 'stock' | 'fund' | 'bond' | 'crypto' | 'deposit' | 'other';
  underlying_asset_type: string;
  quantity: number; purchase_price: number; current_price: number;
  purchase_date: string; sell_date: string; notes: string;
  symbol: string; exchange: string; last_price_update: string | null;
  total_value: number; profit_loss: number;
  created_at: string; updated_at: string;
}

export type InvestmentEventType = 'buy' | 'sell' | 'dividend' | 'fee' | 'adjustment';

export interface InvestmentTransaction {
  id: string; investment_id: string; user_id: string;
  event_type: InvestmentEventType;
  event_date: string;
  quantity: number; unit_price: number; amount: number;
  notes: string;
  created_at: string; updated_at: string;
}

export interface InvestmentNavSnapshot {
  id: number; investment_id: string;
  snapshot_date: string; unit_price: number; quantity_held: number; total_value: number;
}

export interface InvestmentMetrics {
  total_invested: number; total_redeemed: number;
  total_dividends: number; total_fees: number;
  current_value: number; total_pnl: number; total_return_pct: number;
  xirr_annualized: number | null;
  last_1y_xirr: number | null;
  last_1m_xirr: number | null;
  days_held: number; last_event_date: string | null;
}

export interface PortfolioMetrics extends InvestmentMetrics {
  per_product: Record<string, InvestmentMetrics>;
}

export interface InvestmentAnalysisResponse {
  summary: string;
  sentiment: 'bullish' | 'bearish' | 'neutral' | 'mixed';
  sentiment_confidence: number;
  key_findings: string[];
  key_risks: string[];
  notable_developments: string[];
  suggested_action: 'buy' | 'sell' | 'hold' | 'watch' | 'insufficient_data';
  action_confidence: number;
  relevant_indicators: {
    short_term?: 'positive' | 'negative' | 'neutral';
    medium_term?: 'positive' | 'negative' | 'neutral';
    long_term?: 'positive' | 'negative' | 'neutral';
  };
  data_quality: 'high' | 'medium' | 'low';
}

export interface InvestmentAiReport {
  id: string; investment_id: string;
  investment_name: string; investment_symbol: string;
  query: string;
  analysis: InvestmentAnalysisResponse | null;
  raw_articles: { title: string; url: string; source: string | null; date: string | null; snippet: string }[] | null;
  search_backend: string;
  llm_preset_id: string | null;
  llm_model: string | null;
  error: string | null;
  generated_at: string;
}

export interface AnalyzeRequest {
  query?: string;
  days?: number;
  max_results?: number;
}

export interface NetWorthTrend { month: string; net_worth: number; assets: number; liabilities: number }
export interface BurnRate { month: string; income: number; expense: number; burn_rate: number; savings_rate: number }
export interface CumulativeTrend { month: string; cumulative_income: number; cumulative_expense: number; cumulative_balance: number }
export interface SavingsRateTrend { month: string; savings_rate: number }
export interface NecessaryRatioTrend { month: string; necessary_ratio: number }
export interface EmergencyReserveTrend { month: string; coverage_months: number }
export interface NetWorthGrowthTrend { month: string; growth_rate: number; yoy_growth_rate: number }
export interface CategoryTrend { month: string; category_id: string; category_name: string; category_color: string; total: number }
export interface ExpenseVolatility { month: string; total_expense: number; std_dev: number; cv: number }

export interface AssetCompositionTrend { month: string; cash: number; investment_accounts: number; fixed_assets: number; other_assets: number; investment_assets: number; liabilities: number; total_assets: number; net_worth: number }

export interface AiPreset { id: string; user_id: string; name: string; api_url: string; api_key: string; model_name: string; system_prompt: string; is_default: boolean; created_at: string; updated_at: string }

// ---- 校验（Reconciliation）----

export interface ReconciliationIncomeBreakdown { total: number; interest: number }
export interface ReconciliationExpenseBreakdown { net: number; positive: number; refund: number; refund_abs: number }
export interface AccountSummary {
  account_id: string; account_name: string; account_type: string;
  bank_statement_mode: 'direct' | 'composite';
  year: number; month: number;
  income_breakdown: ReconciliationIncomeBreakdown;
  expense_breakdown: ReconciliationExpenseBreakdown;
  transfer_in: number;
  bank_expected: { income: number; expense: number };
}
export interface ExpectedBalance {
  account_id: string; account_name: string;
  expected_balance: number; last_recorded_date: string | null;
  unrecorded_months: string[]; can_check: boolean; hint: string;
}
export interface ReconciliationRecord {
  id: string; account_id: string; year: number; month: number;
  bank_income: number | null; bank_expense: number | null;
  sys_income: number | null; sys_expense: number | null;
  income_diff: number | null; expense_diff: number | null;
  balance_check_expected: number | null; balance_check_actual: number | null; balance_diff: number | null;
  status: 'matched' | 'diff'; notes: string; checked_at: string;
}
export interface InvestmentConsistency {
  accounts: { id: string; name: string; balance: number }[];
  total_account_balance: number; total_invested: number; total_current: number;
  idle_cash: number; status: 'ok' | 'diff'; warnings: string[];
}

export interface NavHistoryPoint { date: string; close: number; ma20: number | null; ma60: number | null }
export interface HealthWarning {
  id?: string | null;
  type: 'loss' | 'concentration';
  severity: 'high' | 'medium' | 'low';
  message: string;
}

export interface HealthResult {
  concentration: {
    max_single_pct: number;
    top3_pct: number;
  };
  allocation: Record<string, number>;
  warnings: HealthWarning[];
}

export interface NavHistoryResponse {
  investment: { id: string; name: string; symbol: string; exchange: string; investment_type: string };
  series: NavHistoryPoint[];
  ma20: (number | null)[];
  ma60: (number | null)[];
  events: InvestmentTransaction[];
  cost_basis: number;
  current_price: number;
  max_drawdown: number;     // decimal, e.g. 0.235 = 23.5%
  source: string;
  begin: string;
  end: string;
}

// ============================================================
// Strategy types (Phase 3)
// ============================================================
export interface StrategyResponse {
  id: string
  name: string
  description: string
  version: number
  params_schema: Record<string, any>
  rebalance_freq: string
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface StrategyImportResult {
  strategy_id: string
  version: number
  status: 'imported' | 'updated'
  error?: string
}

export interface ActiveStrategySet {
  strategy_id: string
  version: number
  params: Record<string, any>
}

export interface ActiveStrategyResponse {
  strategy_id: string
  version: number
  params: Record<string, any>
  name: string
  description: string
  rebalance_freq: string
}
