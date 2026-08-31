export interface User { id: string; email: string; name: string; created_at: string }
export interface BankFormula {
  income: string[]   // 收入侧分项: transfer_in | refund | income
  expense: string[]  // 支出侧分项: expense_positive | expense_net
}
export interface Account { id: string; user_id: string; name: string; currency: string; initial_balance: number; hidden: boolean; sort_order: number; current_balance: number; account_type: string; bank_statement_mode?: string; bank_formula?: BankFormula | null; created_at: string; updated_at: string }
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
  is_money_market: boolean; seven_day_yield: number | null; mmf_shares: number | null;
  total_value: number; profit_loss: number;
  ann_volatility: number | null; sharpe_ratio: number | null; ann_return: number | null;
  created_at: string; updated_at: string;
}

export type InvestmentEventType = 'buy' | 'sell' | 'dividend' | 'fee' | 'adjustment';

export interface InvestmentTransaction {
  id: string; investment_id: string; user_id: string;
  event_type: InvestmentEventType;
  event_date: string;
  quantity: number; unit_price: number; amount: number; fee: number;
  notes: string;
  created_at: string; updated_at: string;
}

export type CashFlowType = 'deposit' | 'withdrawal';

export interface InvestmentCashFlow {
  id: string; user_id: string;
  flow_type: CashFlowType;
  amount: number;
  flow_date: string;
  notes: string | null;
  created_at: string; updated_at: string;
}

export interface ClosedPosition {
  id: string; name: string; symbol: string; exchange: string; investment_type: string;
  purchase_date: string; sell_date: string;
  buy_amount: number; proceeds: number; total_fee: number; cost: number;
  realized_pnl: number; return_rate: number | null;
  days_held: number; ann_return: number | null;
  ann_volatility: number | null; sharpe_ratio: number | null;
}

export interface ClosedPositionsResponse {
  positions: ClosedPosition[];
  total_realized: number; total_cost: number;
  total_return_rate: number | null;
  count: number;
}

export interface PortfolioOverview {
  total_deposits: number;
  total_withdrawals: number;
  old_principal: number;
  principal: number;
  current_market_value: number;
  idle_cash: number;
  total_pnl: number;
  realized_pnl: number;
  dividend_total: number;
  floating_pnl: number;
  total_return_pct: number;
  xirr_annualized: number | null;
  days_held: number;
}

export interface LookupCandidate {
  exchange: string;
  name: string;
  price: number;
  currency: string;
  source: string;
}

export interface RefreshResult {
  id: string; name: string; ok: boolean;
  price?: number; source?: string; error?: string;
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

export interface ReconciliationIncomeBreakdown { total: number }
export interface ReconciliationExpenseBreakdown { net: number; positive: number; refund: number; refund_abs: number }
export interface AccountSummary {
  account_id: string; account_name: string; account_type: string;
  bank_statement_mode: 'direct' | 'composite' | 'custom';
  bank_formula: BankFormula;
  formula_text: string;
  year: number; month: number;
  income_breakdown: ReconciliationIncomeBreakdown;
  expense_breakdown: ReconciliationExpenseBreakdown;
  transfer_in: number;
  bank_expected: { income: number; expense: number };
}
export interface BalancesAsOfRow {
  account_id: string; account_name: string; account_type: string;
  initial_balance: number;
  income: number; expense: number;
  transfer_in: number; transfer_out: number;
  balance: number;
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
  total_account_balance: number;
  total_deposits: number; total_withdrawals: number;
  old_principal: number; principal: number;
  total_current: number; floating_pnl: number;
  realized_pnl: number; dividend_total: number;
  current_month_pnl: number;
  idle_cash: number; diff: number;
  status: 'ok' | 'diff'; warnings: string[];
}

export interface ReconciliationItem {
  label: string;
  value: number;
  operator: '+' | '-' | '';
}

export interface InvestmentReconciliation {
  identity: {
    left_side: { label: string; value: number };
    right_side: {
      items: ReconciliationItem[];
      total: number;
      diff: number;
      passed: boolean;
    };
  };
  auxiliary: {
    market_value: number;
    idle_cash: number;
    idle_cash_check: { label: string; value: number };
    status: 'ok' | 'diff';
    warnings: string[];
  };
  account_checks: {
    account_id: string;
    account_name: string;
    account_type: string;
    initial_balance: number;
    income: number;
    expense: number;
    transfer_in: number;
    transfer_out: number;
    expected_balance: number;
    actual_balance: number;
    diff: number;
    passed: boolean;
  }[];
  flow_checks: {
    deposits: {
      investment_tab_total: number;
      bookkeeping_transfer_in: number;
      initial_balance_deposit: number;
      implied_transfer_in: number;
      diff: number;
    };
    withdrawals: {
      investment_tab_total: number;
      bookkeeping_transfer_out: number;
      diff: number;
    };
  };
  sync_checks: {
    booked_monthly_count: number;
    booked_monthly_total: number;
    first_booked_month: string | null;
    last_booked_month: string | null;
    current_month_skipped: boolean;
  };
}

export interface NavHistoryPoint { date: string; close: number; ma20: number | null; ma60: number | null }
export interface HealthWarning {
  id?: string | null;
  type: 'loss' | 'portfolio_loss';
  severity: 'high' | 'medium' | 'low';
  message: string;
}

export interface HealthResult {
  floating_pnl: number;
  floating_pnl_pct: number;
  total_market_value: number;
  total_cost: number;
  warnings: HealthWarning[];
}

export interface PortfolioNavPoint { date: string; nav: number; total_value: number }
export interface BenchmarkSeriesPoint { date: string; close: number }
export interface BenchmarkInfo {
  name: string;
  symbol: string;
  exchange: string;
  source: string;
  series: BenchmarkSeriesPoint[];
  ann_return: number | null;
  beta: number | null;
  alpha: number | null;
  excess_return: number | null;
}
export interface NavEvent {
  date: string;
  type: 'buy' | 'sell';
  name: string;
  quantity: number;
  amount: number;
}
export interface PortfolioNavResponse {
  series: PortfolioNavPoint[];
  metrics: {
    points: number;
    ann_return: number | null;
    ann_volatility: number | null;
    sharpe: number | null;
    max_drawdown: number | null;
    sortino: number | null;
    calmar: number | null;
    downside_deviation: number | null;
    max_drawdown_duration: number | null;
    recovery_days: number | null;
  };
  funds: { id: string; name: string; symbol: string; source: string }[];
  benchmark: BenchmarkInfo | null;
  events: NavEvent[];
}

export interface PnLHistoryResponse {
  series: { date: string; pnl: number }[];
  granularity: string;
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
  ann_volatility: number | null;
  ann_return: number | null;
  sortino: number | null;
  calmar: number | null;
  downside_deviation: number | null;
  max_drawdown_duration: number | null;   // trading days
  recovery_days: number | null;           // trading days; null = 尚未收复失地
  benchmark: BenchmarkInfo | null;
  source: string;
  begin: string;
  end: string;
}

// ---- 策略（Strategy）----
// ============================================================
// Strategy types (Phase 3)
// ============================================================
export interface StrategyResponse {
  id: string
  name: string
  description: string
  version: number
  params_schema: any
  rebalance_freq: string
  is_builtin: boolean
  folder?: string
  source_file?: string
  group_id?: string | null
  activated_at?: string | null
  version_note?: string | null
  logic?: string | null
  factor_keys?: string[]
  latest_backtest?: {
    backtest_id: string
    status: string
    ann_return: number | null
    sharpe: number | null
    max_drawdown: number | null
    created_at: string | null
  } | null
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

// ---- Research Asset types ----
export interface ResearchAssetIndicators {
  points: number;
  first_date: string | null;
  last_date: string | null;
  latest_close: number | null;
  ret_1m: number | null;       // fraction, e.g. 0.0235
  ret_1y: number | null;
  ann_return: number | null;
  ann_volatility: number | null;
  sharpe: number | null;
  // Trailing 1Y window (same cadence as ret_1y); full-sample ann_* above can
  // diverge sharply from ret_1y when early history drags the long-run mean.
  ann_return_1y: number | null;
  ann_volatility_1y: number | null;
  sharpe_1y: number | null;
  max_drawdown: number | null; // fraction, e.g. -0.2130
}

export interface RedeemRule {
  days: number | null;
  fee_rate: number;
}

export interface ResearchAsset {
  id: string;
  symbol: string;
  exchange: string;
  name: string;
  asset_type: string;
  category: string;
  status: 'watchlist' | 'pooled';
  mgmt_fee: number | null;
  custody_fee: number | null;
  purchase_fee: number | null;
  sales_service_fee: number | null;
  redeem_rules: RedeemRule[];
  redeem_fee_note: string;
  min_purchase: number | null;
  redeem_t_days: number | null;
  liquidity_note: string;
  data_quality: string;
  is_money_market: boolean;
  notes: string | null;
  purchase_limit: number | null;
  purchase_status: string;
  fund_kind: string;
  asset_class: string;
  region: string;
  auto_tags: string[];
  profile_synced_at: string | null;
  indicators: ResearchAssetIndicators;
}

export interface ResearchPricePoint {
  date: string;
  close: number;
  nav: number | null;
  acc_nav: number | null;
}

export interface AssetPriceStatus {
  asset_id: string;
  symbol: string;
  name: string;
  status: string;
  rows: number;
  last_date: string | null;
  last_sync: string | null;
  source: string | null;
  lag_days: number | null;
}

export interface SyncResult {
  asset_id: string;
  rows: number;
  source: string;
  begin: string;
  end: string;
  error: string | null;
}

// ---- 因子（Factor）----

export interface FactorConfig {
  type: 'proxy' | 'spread';
  symbol?: string;
  exchange: string;
  long?: FactorConfig;
  short?: FactorConfig;
}

export interface FactorStat {
  latest_value: number | null;
  latest_level: number | null;
  latest_date: string | null;
  rows: number;
}

export interface FactorResponse {
  id: string;
  name: string;
  category: string;
  definition: string;
  code: string | null;
  data_source: string;
  frequency: string;
  proxy_symbol: string;
  config: FactorConfig | null;
  is_market: boolean;
  active: boolean;
  version: number;
  stats: FactorStat;
}

export interface FactorDetail extends FactorResponse {
  level_series: { date: string; value: number }[];
}

export interface FactorSyncResult {
  factor_id: string;
  name: string;
  rows: number;
  source: string;
  begin: string;
  end: string;
  error: string | null;
}

export interface ExposureCell {
  beta: number;
  t_stat: number | null;
  significant: boolean;
}

export interface AssetExposureRow {
  asset_id: string;
  asset_name: string;
  symbol: string;
  is_money_market: boolean;
  r2: number | null;
  method: string | null;
  n_samples: number | null;
  cells: Record<string, ExposureCell>;
}

export interface ExposureMatrix {
  as_of: string | null;
  factors: FactorResponse[];
  assets: AssetExposureRow[];
  total_assets?: number | null
}

export interface ExposureHistoryPoint {
  as_of_date: string;
  factor_id: string;
  factor_name: string;
  beta: number;
  t_stat: number | null;
  r2: number;
  method: string;
}

export interface ContributionItem {
  factor_id: string;
  factor_name: string;
  beta: number;
  contribution: number | null;
  risk_contribution: number | null;
  sigma_ann: number | null;
}

export interface ContributionResult {
  view: 'return' | 'risk';
  asset_id: string;
  asset_name: string;
  start: string;
  end: string;
  as_of: string | null;
  n_days: number | null;
  total_return: number | null;
  alpha: number | null;
  sum_contributions: number | null;
  identity_residual: number | null;
  explained_vol: number | null;
  items: ContributionItem[];
}

export interface AgentFactorCandidate {
  name: string;
  category: 'asset_class' | 'style' | 'macro' | 'custom';
  definition: string;
  config: FactorConfig;
}

export interface AgentPreviewResult {
  ok: boolean;
  sample_days: number;
  first_date: string | null;
  last_date: string | null;
  latest_level: number | null;
  latest_return: number | null;
  source: string;
  error: string | null;
}

// ---- 信号（Signal）----

export interface SignalTargetDetail {
  symbol: string
  name: string
  weight: number
}

export interface SignalResponse {
  id: string
  strategy_id: string
  strategy_version: number
  strategy_name?: string | null
  run_date: string
  as_of_date: string
  next_rebalance_date: string | null
  target_weights: Record<string, number>  // symbol -> weight
  weights_detail?: SignalTargetDetail[] | null  // 按权重降序，含标的名称
  risk_status: SignalRiskStatus | null
  backtest_id: string | null
  created_at: string
}

export interface SignalRiskStatus {
  alerts: string[]
  warnings: string[]
}

export interface SignalRunResult {
  signal_id: string
  status: 'ok' | 'error'
  error?: string
}

export interface TradePlanRow {
  symbol: string; name: string; current_weight: number; target_weight: number;
  current_mv: number; target_mv: number;
  action: 'buy' | 'sell' | 'hold'; amount: number;
  est_fee_pct: number | null; est_fee_amount: number;
  t_plus: string | null; arrive_date: string | null; warnings: string[];
}

export interface FactorExposurePoint {
  date: string
  exposures: Record<string, number>
}

export interface TradePlan {
  signal_id: string | null; run_date: string | null; next_rebalance_date: string | null;
  invested_value: number; additional_cash: number; total_value: number;
  rows: TradePlanRow[];
}

// ---- 回测（Backtest）----
export interface BacktestGroupMeta {
  id: string
  name: string
  member_count: number
}

export interface BacktestResponse {
  id: string
  strategy_id: string
  strategy_name?: string
  strategy_version: number
  params: Record<string, any>
  universe: string[]
  universe_count?: number
  group_ids?: string[]
  group_names?: BacktestGroupMeta[]
  start_date: string
  end_date: string
  rebalance_freq: string
  data_as_of: string
  status: 'pending' | 'running' | 'done' | 'failed'
  progress?: number
  error?: string
  warning?: string
  factor_keys?: string[]
  created_at: string
  updated_at: string
  results?: BacktestResults
}

export interface BacktestResults {
  nav_series: NavPoint[]
  metrics: BacktestMetrics
  weight_history: WeightSnapshot[]
  rebalance_records: RebalanceRecord[]
  stagnant_analysis?: StagnantAnalysis
  custom_factor_analysis?: Record<string, CustomFactorStat>
  benchmark?: BenchmarkSeries | null
  portfolio_factor_exposures?: PortfolioFactorExposure[]
  factor_exposure_series?: FactorExposurePoint[]
  available_parts?: string[]
  factor_view: FactorView
  risk_view: RiskView
}

export interface NavPoint {
  date: string
  nav: number
  portfolio_value: number
}

export interface BacktestMetrics {
  ann_return: number
  ann_volatility: number
  sharpe: number
  max_drawdown: number
  calmar: number
  sortino: number
  total_cost: number
  total_cost_ratio: number
  turnover_annual: number
  win_rate?: number
  profit_loss_ratio?: number | null
  mdd_duration_days?: number
  beta?: number | null
  alpha_ann?: number | null
  info_ratio?: number | null
  benchmark_ann_return?: number | null
}

export interface BenchmarkSeries {
  name: string
  key: string
  series: { date: string; nav: number }[]
}

export interface PortfolioFactorExposure {
  factor: string
  exposure: number
}

export interface WeightSnapshot {
  date: string
  weights: Record<string, number>
}

export interface RebalanceRecord {
  date: string
  trades: Trade[]
  period_stats?: RebalancePeriodStats
  cumulative_stats?: RebalancePeriodStats
  kind?: 'rebalance' | 'settle'
}

export interface RebalancePeriodStats {
  start_date: string
  end_date: string
  pnl: number
  ret: number
  ann_return: number
  ann_volatility: number
  sharpe?: number | null
  attribution?: { symbol: string; name: string; contribution: number }[]
  factor_attribution?: { factor: string; contribution: number }[]
}

export interface Trade {
  symbol: string  // asset symbol (e.g. "000217"), NOT the internal UUID
  name?: string   // asset display name (e.g. "华安黄金ETF联接C")
  side: 'buy' | 'sell'
  amount: number
  fee: number
}

export interface StagnantAnalysis {
  threshold_ann: number
  windows: number[]
  hits: { window_days: number; start: string; end: string; ann_return: number }[]
  merged_periods: { start: string; end: string }[]
}

export interface CustomFactorStat {
  ic_mean: number
  rank_ic: number
  win_rate: number
  n_periods: number
  horizon_days: number
}

export interface FactorView {
  target_exposure: Record<string, number>
  realized_exposure: Record<string, number>
  contribution: Record<string, number>
}

export interface RiskView {
  max_drawdown_series: { date: string; drawdown: number }[]
  var_95: number
  cvar_95: number
  risk_contrib: Record<string, number>
}

export interface BacktestCreate {
  strategy_id: string
  strategy_version: number
  params: Record<string, any>
  universe: string[]
  start_date: string
  end_date: string
  rebalance_freq: string
}

// ---- 监控（Monitor）----
export interface MonitorOverview {
  zone1_portfolio: Zone1Portfolio
  zone2_risk: Zone2Risk
  zone3_deviation: Zone3Deviation
  alerts_summary: AlertsSummary
  last_updated: string
}

export interface Zone1Portfolio {
  items: PortfolioItem[]
  total_actual_value: number
  alerts: string[]  // asset symbols with deviation alerts
}

export interface PortfolioItem {
  asset_id: string
  symbol: string
  name: string
  target_weight: number    // fraction, e.g. 0.4
  actual_weight: number    // fraction
  deviation: number         // absolute difference
  has_alert: boolean
}

export interface Zone2Risk {
  current_nav: number
  max_drawdown: number         // fraction, e.g. -0.12
  var_95: number               // positive loss fraction
  cvar_95: number             // positive loss fraction
  factor_exposures: FactorExposureRow[]
  drawdown_alert: boolean
}

export interface FactorExposureRow {
  factor_id: string
  factor_name: string
  weighted_beta: number
  risk_contribution: number   // fraction, should sum to ~1.0
}

export interface Zone3Deviation {
  factor_drifts: FactorDriftItem[]
  last_signal_date: string | null
  next_rebalance_date: string | null
  days_since_signal: number | null
  continuity_status: 'ok' | 'stale' | 'no_signal'
}

export interface FactorDriftItem {
  factor_id: string
  factor_name: string
  current_beta: number
  prev_beta: number
  drift: number          // absolute difference
  has_alert: boolean     // drift >= threshold
}

export interface AlertsSummary {
  total_alerts: number
  portfolio_alerts: number
  risk_alerts: number
  deviation_alerts: number
}

export interface MonitorSettings {
  weight_deviation_pp: number
  exposure_drift: number
  drawdown_alert_pct: number
}

export interface ResearchGroup {
  id: string
  name: string
  note: string
  asset_ids: string[]
  members?: { id: string; symbol: string; name: string }[]
}
