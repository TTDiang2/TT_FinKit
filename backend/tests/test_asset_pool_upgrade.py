"""Tests for the asset pool upgrade (2026-08-23 plan):
redeem rule validation, benchmark mapping, statistics pure functions,
and migration idempotency."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from app.schemas.research_asset import RedeemRule, validate_redeem_rules, ResearchAssetPool
from app.routers.research_assets import _pick_benchmark, _rules_to_json, _rules_to_note, _parse_rules_json
from app.routers.research_statistics import _var_cvar, _max_drawdown_path, _rolling_return
from app.models.research_asset import ResearchAsset


def _mk_asset(name: str = "", category: str = "", mmf: bool = False, symbol: str = "000217") -> ResearchAsset:
    return ResearchAsset(
        id="x", user_id="u", symbol=symbol, exchange="FUND_CN", name=name,
        asset_type="fund", category=category, is_money_market=mmf,
    )


class TestRedeemRules:
    def test_validation_ok(self):
        rules = validate_redeem_rules([
            RedeemRule(days=7, fee_rate=1.5), RedeemRule(days=30, fee_rate=0.5),
            RedeemRule(days=None, fee_rate=0),
        ])
        assert len(rules) == 3

    def test_validation_rejects_negative_fee(self):
        with pytest.raises(ValidationError):
            ResearchAssetPool(redeem_rules=[RedeemRule(days=7, fee_rate=-1.0)])

    def test_validation_rejects_non_ascending(self):
        with pytest.raises(ValidationError):
            ResearchAssetPool(redeem_rules=[
                RedeemRule(days=30, fee_rate=0.5), RedeemRule(days=7, fee_rate=1.5),
            ])

    def test_validation_rejects_fallback_not_last(self):
        with pytest.raises(ValidationError):
            ResearchAssetPool(redeem_rules=[
                RedeemRule(days=None, fee_rate=0), RedeemRule(days=7, fee_rate=1.5),
            ])

    def test_rules_to_note(self):
        rules = [RedeemRule(days=7, fee_rate=1.5), RedeemRule(days=None, fee_rate=0)]
        assert _rules_to_note(rules) == "<7天 1.5%，其余 0%"

    def test_json_roundtrip(self):
        rules = [RedeemRule(days=7, fee_rate=1.5), RedeemRule(days=None, fee_rate=0)]
        raw = _rules_to_json(rules)
        back = _parse_rules_json(raw)
        assert back[0].days == 7 and back[0].fee_rate == 1.5
        assert back[1].days is None


class TestBenchmarkMapping:
    def test_gold(self):
        assert _pick_benchmark(_mk_asset(name="易方达黄金ETF联接C")) == ("518880", "SH")

    def test_bond(self):
        assert _pick_benchmark(_mk_asset(name="国债ETF")) == ("bench-cnbd", "IDX")

    def test_overseas(self):
        assert _pick_benchmark(_mk_asset(name="纳指ETF", category="海外")) == ("513100", "SH")

    def test_default_equity(self):
        assert _pick_benchmark(_mk_asset(name="沪深300指数增强")) == ("000300", "SH")

    def test_money_market_none(self):
        assert _pick_benchmark(_mk_asset(name="货币基金B", mmf=True)) is None


class TestStatsFunctions:
    def test_var_cvar(self):
        rets = [0.01, -0.01, 0.02, -0.03, 0.005, -0.02, 0.015, -0.005, 0.0, 0.001]
        var, cvar = _var_cvar(rets, conf=0.95)
        assert var < 0 and cvar <= var  # cvar (tail mean) is more negative than var

    def test_max_drawdown_path(self):
        nav = [1.0, 1.1, 0.9, 0.95]
        dd = _max_drawdown_path(nav)
        assert dd[0] == 0.0
        assert dd[2] == pytest.approx((0.9 - 1.1) / 1.1)

    def test_rolling_return(self):
        rets = [0.01] * 260
        out = _rolling_return(rets, window=252)
        assert out[251] is not None and abs(out[251] - ((1.01 ** 252) - 1)) < 1e-6
        assert out[250] is None  # not enough window yet


class TestMigrationIdempotency:
    def test_migrate_runs_twice(self):
        import subprocess
        script = os.path.join(os.path.dirname(__file__), "..", "scripts", "migrate_asset_pool_upgrade.py")
        # Run against a temp DB copy
        src = os.path.join(os.path.dirname(__file__), "..", "finkit.db")
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            shutil_copy(src, db)
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..")
            for _ in range(2):
                r = subprocess.run([sys.executable, script, db], capture_output=True, text=True, env=env, cwd=os.path.join(os.path.dirname(__file__), ".."))
                assert r.returncode == 0, r.stderr
            conn = sqlite3.connect(db)
            cols = [x[1] for x in conn.execute("PRAGMA table_info(research_assets)")]
            assert "sales_service_fee" in cols and "redeem_rules" in cols
            tables = [x[0] for x in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'research_asset%'")]
            assert "research_asset_ai_reports" in tables
            assert "research_asset_holdings" in tables
            conn.close()


def shutil_copy(src: str, dst: str) -> None:
    import shutil
    shutil.copy2(src, dst)
