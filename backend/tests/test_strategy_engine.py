"""Tests for finkit_strategy package and strategy service."""
import pytest, sys, os, json, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from finkit_strategy.base import Strategy, StrategyContext
from finkit_strategy.runner import run_strategy_in_subprocess
from finkit_strategy.builtin_strategies import BUILTIN_STRATEGIES


class TestStrategyBaseClass:
    def test_strategy_has_required_attrs(self):
        class MyStrat(Strategy):
            name = "TestStrategy"
            description = "A test strategy"
            rebalance_freq = "monthly"
            params_schema = {}
            def target_weights(self, ctx, date): return {}

        s = MyStrat()
        assert s.name == "TestStrategy"
        assert s.description == "A test strategy"
        assert s.rebalance_freq == "monthly"
        assert s.params_schema == {}

    def test_strategy_params_default(self):
        class MyStrat(Strategy):
            name = "T"
            description = ""
            rebalance_freq = "monthly"
            params_schema = {"n": {"type": "int", "default": 3}, "lookback": {"type": "int", "default": 60}}
            def target_weights(self, ctx, date): return {}

        s = MyStrat()
        assert s.params["n"] == 3
        assert s.params["lookback"] == 60

        s2 = MyStrat(n=5, lookback=120)
        assert s2.params["n"] == 5
        assert s2.params["lookback"] == 120

    def test_strategy_universe_default(self):
        class MyStrat(Strategy):
            name = "T"
            description = ""
            rebalance_freq = "monthly"
            params_schema = {}
            def target_weights(self, ctx, date): return {}

        ctx = StrategyContext(pool=[
            {"id": "A", "type": "equity"},
            {"id": "B", "type": "bond"},
        ])
        s = MyStrat()
        assert s.universe(ctx) == ["A", "B"]

    def test_strategy_returns_none_skips_rebalance(self):
        class MyStrat(Strategy):
            name = "T"
            description = ""
            rebalance_freq = "monthly"
            params_schema = {}
            def target_weights(self, ctx, date): return None

        ctx = StrategyContext()
        s = MyStrat()
        assert s.target_weights(ctx, "2025-01-31") is None


class TestStrategyContext:
    def test_momentum_single_asset(self):
        ctx = StrategyContext(
            returns={
                "A": {
                    "2025-01-01": 0.01,
                    "2025-01-02": 0.02,
                    "2025-01-03": -0.01,
                }
            }
        )
        mom = ctx.momentum(["A"], lookback=3)
        expected = 1.01 * 1.02 * 0.99 - 1.0
        assert abs(mom["A"] - expected) < 1e-8

    def test_momentum_partial_lookback(self):
        ctx = StrategyContext(
            returns={
                "A": {
                    "2025-01-01": 0.01,
                    "2025-01-02": 0.02,
                    "2025-01-03": -0.01,
                }
            }
        )
        mom = ctx.momentum(["A"], lookback=2)
        expected = 1.02 * 0.99 - 1.0
        assert abs(mom["A"] - expected) < 1e-8

    def test_volatility_calculation(self):
        ctx = StrategyContext(
            returns={
                "A": {f"2025-01-{d:02d}": 0.01 for d in range(1, 21)}
            }
        )
        vol = ctx.volatility(["A"], lookback=20)
        assert vol["A"] > 0
        assert vol["A"] < 1.0  # sanity check

    def test_nav_history_filter(self):
        ctx = StrategyContext(
            prices={
                "A": {
                    "2025-01-01": 1.0,
                    "2025-01-02": 1.01,
                    "2025-01-03": 0.99,
                    "2025-01-04": 1.02,
                }
            }
        )
        hist = ctx.nav_history(["A"], "2025-01-01", "2025-01-03")
        assert len(hist["A"]) == 3

    def test_factor_exposure(self):
        ctx = StrategyContext(
            factor_exposures={
                "A": {"momentum": 0.5, "size": -0.2},
                "B": {"momentum": 0.3, "size": 0.1},
            }
        )
        assert ctx.factor_exposure("A", "momentum") == 0.5
        assert ctx.factor_exposure("A", "size") == -0.2
        assert ctx.factor_exposure("B", "momentum") == 0.3
        assert ctx.factor_exposure("C", "momentum") == 0.0  # unknown asset

    def test_factor_value(self):
        ctx = StrategyContext(
            factor_values={
                "momentum": {
                    "2025-01-01": 0.01,
                    "2025-01-02": 0.02,
                    "2025-01-03": -0.01,
                }
            }
        )
        fv = ctx.factor_value("momentum", "2025-01-01", "2025-01-03")
        assert len(fv) == 3
        assert fv[0] == ("2025-01-01", 0.01)


class TestRunner:
    def test_run_strategy_returns_weights(self):
        code = '''
from finkit_strategy import Strategy, StrategyContext

class TestStrat(Strategy):
    name = "Test"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return {"A": 0.5, "B": 0.5}
'''
        data = {
            "strategy_code": code,
            "params": {},
            "pool": [],
            "prices": {},
            "returns": {},
            "factor_values": {},
            "factor_exposures": {},
            "current_weights": {},
            "rebalance_dates": ["2025-01-31"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f)
            input_path = f.name
        try:
            result = run_strategy_in_subprocess(input_path, timeout=10)
            assert result["status"] == "ok", f"Expected ok, got: {result}"
            assert "2025-01-31" in result["weights"]
            assert result["weights"]["2025-01-31"] == {"A": 0.5, "B": 0.5}
        finally:
            os.unlink(input_path)

    def test_run_strategy_returns_none_skips(self):
        code = '''
from finkit_strategy import Strategy, StrategyContext

class TestStrat(Strategy):
    name = "Test"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx, date):
        return None
'''
        data = {
            "strategy_code": code,
            "params": {},
            "pool": [],
            "prices": {},
            "returns": {},
            "factor_values": {},
            "factor_exposures": {},
            "current_weights": {},
            "rebalance_dates": ["2025-01-31"],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f)
            input_path = f.name
        try:
            result = run_strategy_in_subprocess(input_path, timeout=10)
            assert result["status"] == "ok"
            assert "2025-01-31" not in result["weights"]  # None means skipped
        finally:
            os.unlink(input_path)


class TestBuiltinStrategies:
    def test_all_builtins_instantiable(self):
        for Strat in BUILTIN_STRATEGIES:
            s = Strat()
            assert s.name
            assert s.rebalance_freq in ("monthly", "weekly")
            assert isinstance(s.params_schema, dict)

    def test_all_builtins_run_without_error(self):
        ctx = StrategyContext(
            pool=[
                {"id": "000300", "type": "equity_index"},
                {"id": "511010", "type": "bond_etf"},
            ],
            returns={
                "000300": {f"2025-01-{d:02d}": 0.01 for d in range(1, 21)},
                "511010": {f"2025-01-{d:02d}": 0.005 for d in range(1, 21)},
            },
            prices={
                "000300": {f"2025-01-{d:02d}": 1.0 + 0.01 * d for d in range(1, 21)},
                "511010": {f"2025-01-{d:02d}": 1.0 + 0.005 * d for d in range(1, 21)},
            },
        )
        for Strat in BUILTIN_STRATEGIES:
            s = Strat()
            w = s.target_weights(ctx, "2025-01-31")
            # None is acceptable (skip rebalance)
            if w is not None:
                assert isinstance(w, dict)
                assert abs(sum(w.values()) - 1.0) < 1e-6 or len(w) == 0


class TestStrategyServiceValidation:
    def test_validate_code_rejects_syntax_error(self):
        from app.services.strategy_service import validate_strategy_code
        ok, msg = validate_strategy_code("class MyStrat(Strategy):\n    pass")
        assert not ok
        assert "name" in msg.lower() or "missing" in msg.lower()

    def test_validate_code_rejects_no_strategy_subclass(self):
        from app.services.strategy_service import validate_strategy_code
        ok, msg = validate_strategy_code("x = 1")
        assert not ok
        assert "Strategy" in msg

    def test_validate_code_accepts_valid_strategy(self):
        from app.services.strategy_service import validate_strategy_code
        code = '''
from finkit_strategy import Strategy

class MyStrategy(Strategy):
    name = "Test"
    description = ""
    rebalance_freq = "monthly"
    params_schema = {}
'''
        ok, msg = validate_strategy_code(code)
        assert ok
