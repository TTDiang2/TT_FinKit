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
        asset_type TEXT, mgmt_fee REAL, custody_fee REAL, purchase_fee REAL
    );
    CREATE TABLE research_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id TEXT, date TEXT, close REAL
    );
    """)
    conn.execute(
        "INSERT INTO research_assets VALUES (?,?,?,?,?,?,?,?)",
        ("A", "161005", "FUND_CN", "Fund A", "fund", 0.0, 0.0, 0.0),
    )
    conn.execute(
        "INSERT INTO research_assets VALUES (?,?,?,?,?,?,?,?)",
        ("B", "511010", "SH", "Bond ETF", "bond_etf", 0.0, 0.0, 0.0),
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
        return {"A": 0.5, "B": 0.5}
'''
            result = _run_backtest_sync(
                strategy_code=code,
                params={},
                universe=["A", "B"],
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
