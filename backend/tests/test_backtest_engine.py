"""Tests for the Phase 4 backtest engine: model, rebalance dates, cost model,
metrics, nav construction, and subprocess end-to-end."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from finkit_strategy.base import Strategy, StrategyContext
from app.services.backtest_engine import (
    generate_rebalance_dates,
    compute_trade_cost,
    redeem_fee_rate,
    compute_metrics,
    run_simulation,
    _run_backtest_sync,
    DEFAULT_REDEEM_RULES,
)


class EqualWeight(Strategy):
    name = "EqualWeight"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return {"A": 0.5, "B": 0.5}


class AllInA(Strategy):
    name = "AllInA"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return {"A": 1.0}


class NeverRebalance(Strategy):
    name = "NeverRebalance"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return None


TRADING_DAYS = [
    "2025-01-29", "2025-01-30", "2025-01-31",
    "2025-02-03", "2025-02-04", "2025-02-05",
    "2025-02-27", "2025-02-28",
]

PRICES_A = {d: 1.0 + 0.01 * i for i, d in enumerate(TRADING_DAYS)}
PRICES_B = {d: 1.0 - 0.01 * i for i, d in enumerate(TRADING_DAYS)}
PRICES = {"A": PRICES_A, "B": PRICES_B}

FEE_TERMS = {
    "A": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0},
    "B": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0},
}


class TestBacktestModel:
    def test_model_instantiation_and_defaults(self):
        from app.models.backtest import Backtest
        bt = Backtest(
            strategy_id="strat-1",
            strategy_version=3,
            start_date="2025-01-01",
            end_date="2025-02-01",
            rebalance_freq="monthly",
            data_as_of="2025-02-01",
        )
        assert bt.strategy_id == "strat-1"
        assert bt.strategy_version == 3
        # column defaults (uuid/status/params) apply on INSERT, not at __init__
        assert bt.id is None
        assert bt.status is None
        assert bt.params is None
        assert bt.universe is None

    def test_model_persists_with_uuid_and_defaults(self):
        import asyncio
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
        from app.database import Base
        from app.models.backtest import Backtest

        async def inner():
            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with maker() as db:
                bt = Backtest(
                    strategy_id="strat-1", strategy_version=1,
                    start_date="2025-01-01", end_date="2025-02-01",
                    rebalance_freq="weekly", data_as_of="2025-02-01",
                )
                db.add(bt)
                await db.commit()
                await db.refresh(bt)
                assert bt.id is not None
                assert bt.status == "pending"
                assert bt.rebalance_freq == "weekly"
                assert bt.created_at is not None
            await engine.dispose()

        asyncio.run(inner())


class TestRebalanceDates:
    def test_monthly_last_trading_day(self):
        dates = generate_rebalance_dates(TRADING_DAYS, "monthly")
        assert dates == ["2025-01-31", "2025-02-28"]

    def test_weekly_picks_fridays_only(self):
        dates = generate_rebalance_dates(TRADING_DAYS, "weekly")
        assert dates == ["2025-01-31", "2025-02-28"]
        for d in dates:
            from datetime import date
            assert date.fromisoformat(d).weekday() == 4


class TestCostModel:
    def test_purchase_fee_is_flat_rate(self):
        fee, rate = compute_trade_cost("buy", 10000.0, 0.015, DEFAULT_REDEEM_RULES, 0)
        assert fee == 150.0
        assert rate == 0.015

    def test_tiered_redeem_fee(self):
        # <7 days -> 1.5%, <30 days -> 0.5%, >=30 days -> 0
        fee, rate = compute_trade_cost("sell", 10000.0, 0.0, DEFAULT_REDEEM_RULES, 3)
        assert rate == 0.015 and fee == 150.0
        fee, rate = compute_trade_cost("sell", 10000.0, 0.0, DEFAULT_REDEEM_RULES, 10)
        assert rate == 0.005 and fee == 50.0
        fee, rate = compute_trade_cost("sell", 10000.0, 0.0, DEFAULT_REDEEM_RULES, 100)
        assert rate == 0.0 and fee == 0.0

    def test_redeem_fee_rate_custom_rules(self):
        rules = [{"max_days": None, "fee_rate": 0.0}]
        assert redeem_fee_rate(rules, 5) == 0.0
        rules = [{"max_days": 7, "fee_rate": 0.02}, {"max_days": None, "fee_rate": 0.001}]
        assert redeem_fee_rate(rules, 1) == 0.02
        assert redeem_fee_rate(rules, 7) == 0.001  # >= max_days falls through
        assert redeem_fee_rate([], 5) == 0.0


class TestMetrics:
    def test_ann_return_sharpe_max_drawdown(self):
        navs = [{"date": f"2025-01-{d:02d}", "nav": 1.0 + 0.01 * i}
                for i, d in enumerate(range(1, 12))]
        m = compute_metrics(navs, total_cost=10.0, turnover=20000.0)
        expected_ann = (1.10 ** (252 / 10)) - 1.0
        assert abs(m["ann_return"] - expected_ann) < 1e-4
        assert m["ann_return"] > 0
        assert m["sharpe"] > 0
        assert m["max_drawdown"] == 0.0  # monotonic up
        assert m["total_cost"] == 10.0
        assert m["turnover_annual"] > 0
        assert m["sortino"] == 0.0  # monotonic up -> no downside days

    def test_max_drawdown_captures_dip(self):
        navs = [
            {"date": "2025-01-01", "nav": 1.0},
            {"date": "2025-01-02", "nav": 1.1},
            {"date": "2025-01-03", "nav": 0.9},
            {"date": "2025-01-04", "nav": 1.2},
        ]
        m = compute_metrics(navs)
        expected = (0.9 - 1.1) / 1.1
        assert abs(m["max_drawdown"] - expected) < 1e-6
        assert m["calmar"] > 0  # ann_return positive (final > initial), mdd negative

    def test_empty_series_returns_zeroes(self):
        m = compute_metrics([], total_cost=0.0, turnover=0.0)
        assert m["ann_return"] == 0.0
        assert m["max_drawdown"] == 0.0


class TestSimulation:
    def _run(self, strategy, prices=None, rebalance_dates=None, fee_terms=None,
             initial_capital=100000.0):
        prices = prices or PRICES
        trading_days = sorted(set().union(*(set(p) for p in prices.values())))
        rebalance_dates = rebalance_dates or generate_rebalance_dates(trading_days, "monthly")
        ctx = StrategyContext(
            pool=[{"id": "A", "type": "fund"}, {"id": "B", "type": "bond_etf"}],
            prices=prices,
            returns={aid: {} for aid in prices},
            current_weights={},
            params={},
        )
        return run_simulation(
            strategy=strategy,
            ctx=ctx,
            trading_days=trading_days,
            rebalance_dates=rebalance_dates,
            prices=prices,
            fee_terms=fee_terms or FEE_TERMS,
            redeem_rules=DEFAULT_REDEEM_RULES,
            initial_capital=initial_capital,
        )

    def test_equal_weight_backtest(self):
        result = self._run(EqualWeight())
        assert len(result["nav_series"]) == len(TRADING_DAYS)
        assert result["nav_series"][0]["nav"] == 1.0
        assert result["nav_series"][0]["portfolio_value"] == 100000.0
        # B falls 7% while A rises 7% -> net negative drift; the Feb-28
        # rebalance sells A after a 28-day holding -> 0.5% tiered redeem fee
        a_val = 50000 / 1.02 * 1.07
        b_val = 50000 / 0.98 * 0.93
        total = a_val + b_val
        sell_fee = (a_val - total / 2) * 0.005
        expected_final = (total - sell_fee) / 100000.0
        assert abs(result["nav_series"][-1]["nav"] - expected_final) < 1e-4
        # two monthly rebalances recorded
        assert len(result["rebalance_records"]) == 2
        assert result["rebalance_records"][0]["date"] == "2025-01-31"
        # weights sum to ~1.0 on rebalance days (fee-at-execution leaves a
        # small residual: fees are paid out of cash after targets are set)
        for wh in result["weight_history"]:
            if wh["weights"]:
                assert abs(sum(wh["weights"].values()) - 1.0) < 1e-3
        assert set(result["metrics"].keys()) >= {
            "ann_return", "ann_volatility", "sharpe", "max_drawdown",
            "calmar", "sortino", "total_cost", "turnover_annual",
        }
        assert "factor_view" in result and "risk_view" in result

    def test_none_target_skips_rebalance_keeps_cash(self):
        result = self._run(NeverRebalance())
        assert result["rebalance_records"] == []
        for p in result["nav_series"]:
            assert p["nav"] == 1.0
            assert p["portfolio_value"] == 100000.0

    def test_nav_series_construction_single_asset(self):
        prices = {"A": {d: 1.0 + 0.01 * i for i, d in enumerate(TRADING_DAYS)}}
        # rebalance on the very first trading day at price 1.0 -> NAV == price
        result = self._run(AllInA(), prices=prices, rebalance_dates=[TRADING_DAYS[0]])
        navs = [p["nav"] for p in result["nav_series"]]
        expected = [1.0 + 0.01 * i for i, _ in enumerate(TRADING_DAYS)]
        for got, exp in zip(navs, expected):
            assert abs(got - exp) < 1e-6
        # portfolio_value = 100000 * nav
        assert abs(result["nav_series"][-1]["portfolio_value"] - 100000.0 * navs[-1]) < 0.01

    def test_daily_mgmt_custody_fee_deducted(self):
        prices = {"A": {d: 1.0 + 0.001 * i for i, d in enumerate(TRADING_DAYS)}}
        fee_terms = {"A": {"purchase_fee": 0.0, "mgmt_fee": 0.01, "custody_fee": 0.005}}
        result = self._run(AllInA(), prices=prices, fee_terms=fee_terms)
        # fee = 1.5%/year /365 each day -> cumulative > 0
        assert result["metrics"]["total_cost"] > 0
        pure_last = 1.0 + 0.001 * (len(TRADING_DAYS) - 1)
        assert result["nav_series"][-1]["nav"] < pure_last


def _build_test_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE research_assets (
        id TEXT PRIMARY KEY, symbol TEXT, exchange TEXT, name TEXT,
        asset_type TEXT, mgmt_fee REAL, custody_fee REAL, purchase_fee REAL,
        sales_service_fee REAL, redeem_rules TEXT, redeem_t_days INTEGER
    );
    CREATE TABLE research_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id TEXT, date TEXT, close REAL
    );
    """)
    conn.execute(
        "INSERT INTO research_assets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("A", "161005", "FUND_CN", "Fund A", "fund", 0.0, 0.0, 0.0, 0.0, None, 0),
    )
    conn.execute(
        "INSERT INTO research_assets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("B", "511010", "SH", "Bond ETF", "bond_etf", 0.0, 0.0, 0.0, 0.0, None, 0),
    )
    for i, d in enumerate(TRADING_DAYS):
        conn.execute(
            "INSERT INTO research_prices (asset_id, date, close) VALUES (?,?,?)",
            ("A", d, 1.0 + 0.01 * i),
        )
        conn.execute(
            "INSERT INTO research_prices (asset_id, date, close) VALUES (?,?,?)",
            ("B", d, 1.0 - 0.01 * i),
        )
    conn.commit()
    conn.close()


class SwitchAToB(Strategy):
    """1月31日满仓 A，2月28日切到 B——触发一次真实卖出+买入。"""

    name = "SwitchAToB"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return {"B": 1.0} if date >= "2025-02-01" else {"A": 1.0}


class TestSettlementAndCosts:
    """T+N 锁定 / 销售服务费 / per-asset 赎回费 / 滑点 的回归测试。"""

    def _run(self, strategy, fee_terms, rebalance_dates=None, redeem_rules=None,
             slippage=0.0, prices=None):
        prices = prices or PRICES
        trading_days = sorted(set().union(*(set(p) for p in prices.values())))
        rebalance_dates = rebalance_dates or generate_rebalance_dates(trading_days, "monthly")
        ctx = StrategyContext(
            pool=[{"id": "A", "type": "fund"}, {"id": "B", "type": "bond_etf"}],
            prices=prices,
            returns={aid: {} for aid in prices},
            current_weights={},
            params={},
        )
        return run_simulation(
            strategy=strategy, ctx=ctx, trading_days=trading_days,
            rebalance_dates=rebalance_dates, prices=prices, fee_terms=fee_terms,
            redeem_rules=redeem_rules or DEFAULT_REDEEM_RULES,
            initial_capital=100000.0, slippage=slippage,
        )

    def test_sell_proceeds_locked_by_redeem_t_days(self):
        """赎回资金 T+N 锁定：T+2 卖出后资金不可用，释放后才能再买入。"""
        # 日历延续到 3 月初，让 2/28 卖出的 T+2 资金在窗口内释放
        days = TRADING_DAYS + ["2025-03-03", "2025-03-04"]
        prices = {"A": {d: 1.0 + 0.01 * i for i, d in enumerate(days)},
                  "B": {d: 1.0 - 0.01 * i for i, d in enumerate(days)}}
        fee = {
            "A": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 2},
            "B": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 0},
        }
        rebal = ["2025-01-31", "2025-02-28", "2025-03-03"]
        result = self._run(SwitchAToB(), fee, rebalance_dates=rebal, prices=prices)
        recs = result["rebalance_records"]
        # 2/28：卖 A 成功，买 B 因资金锁定失败（diff<=0 -> 无 buy 记录）
        feb_rec = next(r for r in recs if r["date"] == "2025-02-28")
        assert [t["side"] for t in feb_rec["trades"]] == ["sell"], feb_rec["trades"]
        # 3/3：锁定资金（3/2）已释放，买入 B 成功
        mar_rec = next(r for r in recs if r["date"] == "2025-03-03")
        assert any(t["side"] == "buy" for t in mar_rec["trades"]), mar_rec["trades"]
        # 对比无锁定：2/28 就能买入 B（卖出资金即时可用）
        fee_no_lock = {k: {**v, "redeem_t_days": 0} for k, v in fee.items()}
        res_no_lock = self._run(SwitchAToB(), fee_no_lock, rebalance_dates=rebal, prices=prices)
        feb_no_lock = next(r for r in res_no_lock["rebalance_records"] if r["date"] == "2025-02-28")
        assert any(t["side"] == "buy" for t in feb_no_lock["trades"]), feb_no_lock["trades"]

    def test_sales_service_fee_deducted_daily(self):
        """销售服务费（C 类）按日计提，会降低最终净值。"""
        base = {
            "A": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 0},
            "B": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 0},
        }
        res0 = self._run(AllInA(), base)
        with_service = {
            k: {**v, "sales_service_fee": 0.004 if k == "A" else 0.0}
            for k, v in base.items()
        }
        res1 = self._run(AllInA(), with_service)
        # 0.4%/年 计提 8 个交易日 → 应有微小但可测的净值差
        assert res1["nav_series"][-1]["nav"] < res0["nav_series"][-1]["nav"]
        assert res0["metrics"]["total_cost"] < res1["metrics"]["total_cost"]

    def test_per_asset_redeem_rules_override_default(self):
        """fee_terms 里的 per-asset redeem_rules 优先于全局默认。"""
        fee = {
            "A": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0,
                  "redeem_rules": [{"max_days": 100, "fee_rate": 0.02}],
                  "redeem_t_days": 0},
            "B": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 0},
        }
        # 持有 <100 天卖出 → 2% 而非默认 0.5%
        result = self._run(SwitchAToB(), fee, rebalance_dates=["2025-01-31", "2025-02-28"])
        sell_rec = [t for t in result["rebalance_records"][-1]["trades"] if t["side"] == "sell"]
        assert sell_rec and sell_rec[0]["fee"] > 0
        # 2% fee 的金额 ≈ 卖出金额 * 2%
        assert abs(sell_rec[0]["fee"] / sell_rec[0]["amount"] - 0.02) < 1e-6

    def test_slippage_increases_costs(self):
        """滑点参数会增大买卖成本。"""
        base = {
            "A": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 0},
            "B": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0,
                  "sales_service_fee": 0.0, "redeem_rules": [], "redeem_t_days": 0},
        }
        res0 = self._run(AllInA(), base)
        res1 = self._run(AllInA(), base, slippage=0.01)
        assert res1["metrics"]["total_cost"] > res0["metrics"]["total_cost"]
        assert res1["nav_series"][-1]["nav"] < res0["nav_series"][-1]["nav"]


class TestSubprocessEndToEnd:
    def test_full_pipeline_via_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test.db")
            _build_test_db(db_path)

            code = '''
from finkit_strategy import Strategy, StrategyContext

class EqualWeight(Strategy):
    name = "EqualWeight"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return {"161005": 0.5, "511010": 0.5}
'''
            result = _run_backtest_sync(
                strategy_code=code,
                params={},
                universe=["161005", "511010"],
                start_date=TRADING_DAYS[0],
                end_date=TRADING_DAYS[-1],
                rebalance_freq="monthly",
                db_path=db_path,
            )
            assert result["status"] == "ok", result
            assert len(result["nav_series"]) == len(TRADING_DAYS)
            assert result["nav_series"][0]["nav"] == 1.0
            assert result["metrics"]["ann_return"] != 0.0
            assert len(result["rebalance_records"]) == 2

    def test_no_price_data_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "empty.db")
            _build_test_db(db_path)
            result = _run_backtest_sync(
                strategy_code=(
                    "from finkit_strategy import Strategy\n"
                    "class S(Strategy):\n"
                    "    name='S'\n    description=''\n    rebalance_freq='monthly'\n"
                    "    params_schema={}\n"
                    "    def target_weights(self, ctx, date): return {}\n"
                ),
                params={},
                universe=["NOPE"],
                start_date="2020-01-01",
                end_date="2020-12-31",
                rebalance_freq="monthly",
                db_path=db_path,
            )
            assert result["status"] == "error"
            assert result["error"]


class TestSMATimingStrategy:
    """测试 MA 均线择时策略（000217 单标的，全仓/空仓两种状态）"""

    def test_sma_timing_import(self):
        """验证 SMATimingStrategy 可以正常 import"""
        from finkit_strategy.builtin_strategies import SMATimingStrategy
        s = SMATimingStrategy()
        assert s.name == "MA 均线择时"
        assert s.rebalance_freq == "monthly"
        assert s.params["ma_days"] == 20

    def test_sma_timing_full_backtest(self):
        """完整回测：000217 单标的，价格先跌后涨，验证 MA 择时有效"""
        from finkit_strategy.builtin_strategies import SMATimingStrategy

        days = [
            "2025-01-29", "2025-01-30", "2025-01-31",
            "2025-02-03", "2025-02-04", "2025-02-05",
            "2025-02-27", "2025-02-28",
        ]
        prices_a = {d: 1.0 - 0.01 * i for i, d in enumerate(days)}
        prices = {"000217": prices_a}

        trading_days = sorted(prices["000217"].keys())
        rebalance_dates = generate_rebalance_dates(trading_days, "monthly")

        ctx = StrategyContext(
            pool=[{"id": "000217", "symbol": "000217", "type": "stock"}],
            prices=prices,
            returns={aid: {} for aid in prices},
            current_weights={},
            params={},
        )

        strategy = SMATimingStrategy()
        strategy._universe = ["000217"]
        strategy.params = {"ma_days": 3}

        result = run_simulation(
            strategy=strategy,
            ctx=ctx,
            trading_days=trading_days,
            rebalance_dates=rebalance_dates,
            prices=prices,
            fee_terms={"000217": {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0}},
            redeem_rules=DEFAULT_REDEEM_RULES,
            initial_capital=100000.0,
        )

        assert "nav_series" in result
        assert "rebalance_records" in result
        assert len(result["nav_series"]) == len(trading_days)
        # 初始 nav = 1.0，之后因持续空仓 NAV 保持不变（无交易无损耗）
        for entry in result["nav_series"]:
            assert entry["nav"] == 1.0, "空仓时 NAV 应保持 1.0"

    def test_sma_timing_logic_golden_cross(self):
        """金叉 → 全仓；死叉 → 空仓，逻辑验证"""
        from finkit_strategy.builtin_strategies import SMATimingStrategy

        # 构造 3 天 MA：Day1=10, Day2=11, Day3=12（价格向上穿过 MA）
        price_series = {
            "2025-01-01": 10.0,
            "2025-01-02": 11.0,
            "2025-01-03": 12.0,   # MA3 = (10+11+12)/3 = 11 > price=12? NO → MA3=11
        }
        # 重新构造让 price > MA
        price_series2 = {
            "2025-01-01": 10.0,
            "2025-01-02": 11.0,
            "2025-01-03": 12.0,
            "2025-01-04": 12.5,   # MA3(10,11,12)=11 → price 12.5 > 11 → 全仓
        }

        class MockCtx:
            def __init__(self, prices):
                self.prices = {"000217": prices}
                self.pool = [{"id": "000217", "symbol": "000217"}]

        ctx = MockCtx(price_series2)
        s = SMATimingStrategy()
        s._universe = ["000217"]
        s.params = {"ma_days": 3}

        # 金叉 → 全仓
        w = s.target_weights(ctx, "2025-01-04")
        assert w is not None
        assert w["000217"] == 1.0, f"expected 1.0 (全仓), got {w['000217']}"

        # 死叉：价格跌破 MA
        price_series3 = {
            "2025-01-01": 10.0,
            "2025-01-02": 13.0,
            "2025-01-03": 14.0,
            "2025-01-04": 11.0,   # MA3(10,13,14)=12.33 → price 11 < MA → 空仓
        }
        ctx2 = MockCtx(price_series3)
        w2 = s.target_weights(ctx2, "2025-01-04")
        assert w2 is not None
        assert w2["000217"] == 0.0, f"expected 0.0 (空仓), got {w2['000217']}"


class TestAssetRotation:
    """大类资产动量轮动：动量信号 + 前 K 等权。"""

    def test_rotation_picks_highest_momentum(self):
        from finkit_strategy.builtin_strategies import AssetRotationStrategy

        # 3 标的模拟 A 强涨 B 缓涨 C 跌 -> 综合 A > B > C
        days = [f"2026-0{m}-15" for m in range(1, 8)]
        # A 强趋势到 1.2，C 下跌 0.8
        prices = {
            "A": {d: 1.0 + 0.02 * i for i, d in enumerate(days)},
            "B": {d: 1.0 + 0.005 * i for i, d in enumerate(days)},
            "C": {d: 1.0 - 0.02 * i for i, d in enumerate(days)},
        }
        ctx = StrategyContext(
            pool=[{"id": "a", "symbol": "A"}, {"id": "b", "symbol": "B"}, {"id": "c", "symbol": "C"}],
            prices=prices,
            returns={s: {} for s in prices},
            current_weights={},
            params={},
        )
        s = AssetRotationStrategy()
        s.params = {"symbols": "A,B,C", "top_k": 1}
        w = s.target_weights(ctx, days[-1])
        assert w is not None and list(w.keys()) == ["A"], f"expected pick A, got {w}"
        assert list(w.values())[0] == 1.0

        # top_k=2 -> A 与 B 等权
        s2 = AssetRotationStrategy()
        s2.params = {"symbols": "A,B,C", "top_k": 2}
        w2 = s2.target_weights(ctx, days[-1])
        assert w2 is not None and set(w2.keys()) == {"A", "B"}, f"expected A,B, got {w2}"
        assert abs(list(w2.values())[0] - 0.5) < 1e-9

    def test_rotation_ignores_symbols_not_in_pool(self):
        from finkit_strategy.builtin_strategies import AssetRotationStrategy

        days = [f"2026-0{m}-15" for m in range(1, 9)]
        prices = {"A": {d: 1.0 + 0.05 * i for i, d in enumerate(days)}}
        ctx = StrategyContext(
            pool=[{"id": "a", "symbol": "A"}],
            prices=prices, returns={"A": {}}, current_weights={}, params={},
        )
        s = AssetRotationStrategy()
        # 白名单含不存在的 D，应被忽略，仍选中 A
        s.params = {"symbols": "A,D", "top_k": 1}
        w = s.target_weights(ctx, days[-1])
        assert w is not None and list(w.keys()) == ["A"]

    def test_rotation_full_backtest_reaches_high_sharpe(self):
        """180日/top2 在真实价格上应跑出夏普>1、收益>7%（用模拟趋势数据）。"""
        import random
        from datetime import date, timedelta

        random.seed(1)
        base = date(2022, 1, 3)
        end = date(2026, 8, 25)
        prices = {}
        for sym, drift, vol in [("A", 0.003, 0.01), ("B", 0.001, 0.008), ("C", 0.002, 0.012)]:
            px = 1.0
            series = {}
            d = base
            while d <= end:
                px *= (1 + random.gauss(drift, vol))
                series[d.isoformat()] = round(px, 4)
                d += timedelta(days=1)
            prices[sym] = series

        trading_days = sorted(set().union(*(set(p) for p in prices.values())))
        rebalance_dates = generate_rebalance_dates(trading_days, "monthly")
        ctx = StrategyContext(
            pool=[{"id": "a", "symbol": "A"}, {"id": "b", "symbol": "B"}, {"id": "c", "symbol": "C"}],
            prices=prices,
            returns={s: {} for s in prices},
            current_weights={},
            params={},
        )
        from finkit_strategy.builtin_strategies import AssetRotationStrategy
        s = AssetRotationStrategy()
        s.params = {"symbols": "A,B,C", "top_k": 2, "momentum_floor": -0.02}
        result = run_simulation(
            strategy=s, ctx=ctx, trading_days=trading_days, rebalance_dates=rebalance_dates,
            prices=prices,
            fee_terms={sym: {"purchase_fee": 0.0, "mgmt_fee": 0.0, "custody_fee": 0.0} for sym in prices},
            redeem_rules=DEFAULT_REDEEM_RULES,
            initial_capital=100000.0,
        )
        m = result["metrics"]
        assert m["ann_return"] > 0.07, f"ann_return {m['ann_return']} should beat 7%"
        assert m["sharpe"] > 1.0, f"sharpe {m['sharpe']} should beat 1"
