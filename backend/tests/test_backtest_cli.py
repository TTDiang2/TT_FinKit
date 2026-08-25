"""Tests for scripts/run_backtest_cli.py — the agent-facing backtest CLI.

Verifies the CLI produces a parseable JSON envelope with expected metrics
and a human summary on stderr, reusing the real engine subprocess path.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

STRATEGY_PY = '''
from finkit_strategy import Strategy, StrategyContext

class AssetRotationStrategy(Strategy):
    name = "大类资产动量轮动"
    description = "月度按过去 N 个交易日涨幅选最强 K 个大类资产等权持有"
    rebalance_freq = "monthly"
    params_schema = {
        "symbols": {"type": "str", "default": "000217,000667,002910,006432,378546"},
        "lookback_days": {"type": "int", "default": 180, "min": 20, "max": 500},
        "top_k": {"type": "int", "default": 2, "min": 1, "max": 6},
    }

    def target_weights(self, ctx, date):
        pool_symbols = {a["symbol"] for a in ctx.pool}
        symbols = [s.strip() for s in self.params["symbols"].split(",") if s.strip()]
        candidates = [s for s in symbols if s in pool_symbols]
        if not candidates:
            return None
        lookback = self.params["lookback_days"]
        momentum = {}
        for sym in candidates:
            series = ctx.prices.get(sym, {})
            dates = sorted(d for d in series.keys() if d <= date)
            if len(dates) < 2:
                continue
            window = dates[-(lookback + 1):] if len(dates) > lookback else dates
            base = series[window[0]]
            latest = series[window[-1]]
            if base and base > 0:
                momentum[sym] = latest / base - 1.0
        if not momentum:
            return None
        top = sorted(momentum, key=momentum.get, reverse=True)[: self.params["top_k"]]
        w = 1.0 / len(top)
        return {sym: w for sym in top}
'''


@pytest.fixture()
def strategy_file(tmp_path):
    p = tmp_path / "strategy.py"
    p.write_text(STRATEGY_PY, encoding="utf-8")
    return str(p)


def _run_cli(strategy_file: str, *extra: str) -> subprocess.CompletedProcess:
    cli = os.path.join(_BACKEND, "scripts", "run_backtest_cli.py")
    db = os.path.join(_BACKEND, "finkit.db")
    cmd = [
        sys.executable, cli,
        "--strategy-file", strategy_file,
        "--universe", "000217,000667,002910,006432,378546",
        "--start", "2021-09-01", "--end", "2026-08-25",
        "--db", db,
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)


class TestRunBacktestCli:
    def test_stdout_is_json_with_metrics(self, strategy_file):
        res = _run_cli(strategy_file, '--params', '{"lookback_days":180,"top_k":2}')
        assert res.returncode == 0, f"stderr: {res.stderr}"
        data = json.loads(res.stdout)
        assert data["status"] == "ok"
        # 含真实费率（C 类销售服务费/赎回档位/T+N 锁定）后夏普显著低于
        # 未计费版本，但策略仍应正收益——断言只要求仍盈利
        assert data["metrics"]["sharpe"] > 0.5
        assert data["metrics"]["ann_return"] > 0.05
        assert len(data["nav_series"]) > 500
        assert len(data["weight_history"]) == len(data["nav_series"])
        # human summary present on stderr
        assert "sharpe=" in res.stderr
        assert "ann_return=" in res.stderr

    def test_rebalance_freq_defaults_to_strategy(self, strategy_file):
        # No --freq passed -> CLI should use the strategy's own monthly
        res = _run_cli(strategy_file, '--params', '{"lookback_days":180,"top_k":2}')
        data = json.loads(res.stdout)
        assert data["rebalance_freq"] == "monthly"

    def test_missing_strategy_file_fails_cleanly(self, tmp_path):
        res = _run_cli(str(tmp_path / "nope.py"))
        assert res.returncode == 1
        assert "ERROR" in res.stderr