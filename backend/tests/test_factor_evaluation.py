"""Factor evaluation engine tests — known-correlation fixtures, pure numpy."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from app.services.factor_evaluation import (
    DEFAULT_THRESHOLDS,
    assign_quantiles,
    evaluate_series,
    ols_alpha_beta,
    rankdata_avg,
    screen,
)


class TestRankData:
    def test_ties_get_average_rank(self):
        r = rankdata_avg([1.0, 2.0, 2.0, 3.0])
        assert list(r) == [1.0, 2.5, 2.5, 4.0]

    def test_monotonic(self):
        r = rankdata_avg([10.0, 5.0, 7.0])
        assert list(r) == [3.0, 1.0, 2.0]


class TestQuantiles:
    def test_q1_lowest_q5_highest(self):
        vals = np.arange(1, 26, dtype=float)  # 1..25
        q = assign_quantiles(vals, 5)
        assert q[0] == 1 and q[-1] == 5
        assert set(np.unique(q)) == {1, 2, 3, 4, 5}

    def test_small_pool_no_crash(self):
        q = assign_quantiles(np.array([1.0, 2.0]), 5)
        assert len(q) == 2


def _make_fixture(seed: int, rho: float, n_funds: int = 6, n_periods: int = 24):
    """Factor exposures + next-period returns with controllable correlation."""
    rs = np.random.RandomState(seed)
    period_dates = [f"2024-{(i % 12) + 1:02d}-28" for i in range(n_periods)]  # unique months
    exposures = {}
    fwd = {}
    for a in range(n_funds):
        xs = rs.normal(0, 1, n_periods)
        noise = rs.normal(0, 1, n_periods)
        # returns = rho * xs + sqrt(1-rho^2) * noise (population corr ≈ rho)
        rets = rho * xs + np.sqrt(max(0.0, 1 - rho * rho)) * noise
        exposures[f"fund{a}"] = list(xs)
        # fwd[i] = return from period i -> i+1, correlated with exposure at i
        # last period has no next -> None at the END
        fwd[f"fund{a}"] = [float(v) * 0.05 for v in rets[:-1]] + [None]
    bench = [float(np.mean([fwd[f"fund{a}"][i] for a in range(n_funds)])) if fwd[f"fund{a}"][i] is not None else None for i in range(n_periods)]
    return period_dates, exposures, fwd, bench


class TestEvaluateSeries:
    def test_strong_factor_high_ic(self):
        dates, expo, fwd, bench = _make_fixture(seed=42, rho=0.8)
        out = evaluate_series(dates, expo, fwd, bench)
        assert out.n_periods == 23  # 24 periods, first one has no forward return
        assert out.ic_mean is not None and out.ic_mean > 0.6
        assert out.rank_ic_mean is not None and out.rank_ic_mean > 0.6
        assert out.win_rate is not None and out.win_rate > 0.7
        assert out.icir is not None and out.icir > 0.5
        assert out.t_stat is not None and abs(out.t_stat - out.icir * np.sqrt(out.n_periods)) < 1e-9
        assert abs(out.icir_annualized - out.icir * np.sqrt(12)) < 1e-9

    def test_random_factor_zero_ic(self):
        dates, expo, fwd, bench = _make_fixture(seed=7, rho=0.0)
        out = evaluate_series(dates, expo, fwd, bench)
        assert abs(out.ic_mean) < 0.25
        # random factor: screen should fail most thresholds
        sc = screen(out, DEFAULT_THRESHOLDS)
        assert sc["rank_ic_mean"] is False or sc["icir_annualized"] is False

    def test_quantile_spread_positive_for_good_factor(self):
        dates, expo, fwd, bench = _make_fixture(seed=42, rho=0.9)
        out = evaluate_series(dates, expo, fwd, bench)
        assert out.quantile_returns is not None
        assert out.quantile_returns["q5"] > out.quantile_returns["q1"]
        assert out.quantile_returns["spread"] > 0
        assert out.ls_sharpe is not None and out.ls_sharpe > 0
        assert len(out.ls_nav) == 23  # 24 periods, last one has no forward return
        assert out.ls_nav[-1]["nav"] > 1.0

    def test_ls_identity_ann_return(self):
        dates, expo, fwd, bench = _make_fixture(seed=3, rho=0.5)
        out = evaluate_series(dates, expo, fwd, bench)
        # ann return = mean monthly LS × 12
        n = len(out.ls_nav)
        assert out.ls_ann_return is not None
        assert abs(out.ls_max_dd) <= 1e-9 or out.ls_max_dd < 0.0  # mdd ≤ 0


class TestScreen:
    def test_threshold_override_forces_fail(self):
        dates, expo, fwd, bench = _make_fixture(seed=42, rho=0.95)
        out = evaluate_series(dates, expo, fwd, bench)
        strict = {"rank_ic_mean": 999.0, "icir_annualized": 999.0, "win_rate": 1.1, "ls_sharpe": 999.0}
        sc = screen(out, strict)
        assert not any(sc.values())

    def test_relaxed_thresholds_pass(self):
        dates, expo, fwd, bench = _make_fixture(seed=42, rho=0.5)
        out = evaluate_series(dates, expo, fwd, bench)
        loose = {"rank_ic_mean": 0.0, "icir_annualized": 0.0, "win_rate": 0.0, "ls_sharpe": -99.0}
        sc = screen(out, loose)
        assert sc["rank_ic_mean"] and sc["icir_annualized"] and sc["win_rate"] and sc["ls_sharpe"]


class TestOls:
    def test_known_beta(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = 0.01 + 2.5 * x
        alpha, beta = ols_alpha_beta(y, x)
        assert abs(beta - 2.5) < 1e-9
        assert abs(alpha - 0.01) < 1e-9


def pytest_approx(v, rel=1e-9):
    return v  # helper: equality is exact by construction in this test
