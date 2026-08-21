from app.services.indicators import (
    annualized_volatility,
    beta_alpha,
    calmar_ratio,
    downside_deviation,
    max_drawdown_duration,
    recovery_days,
    sortino_ratio,
)


def test_downside_deviation_only_negative_returns():
    # [100, 90, 95, 85]: daily returns -10%, +5.56%, -10.53% → only negatives counted
    vol = annualized_volatility([100, 90, 95, 85])
    dd = downside_deviation([100, 90, 95, 85])
    assert dd is not None and dd > 0
    assert vol is not None and vol > 0
    assert dd < vol  # subset of returns → smaller sample std


def test_downside_deviation_none_without_negative_days():
    assert downside_deviation([100, 101, 102]) is None


def test_sortino_ratio_none_when_no_downside():
    assert sortino_ratio([100, 101, 102]) is None


def test_sortino_ratio_finite():
    s = sortino_ratio([100, 90, 95, 85])
    assert s is not None


def test_calmar_ratio_none_when_no_drawdown():
    assert calmar_ratio([100, 101, 102]) is None


def test_calmar_ratio_finite_on_drawdown():
    c = calmar_ratio([100, 90])
    assert c is not None and c < 0


def test_max_drawdown_duration_peak_to_trough():
    # peak 110 at idx 1, deepest trough 90 at idx 3 → 2 trading days
    assert max_drawdown_duration([100, 110, 105, 90, 95]) == 2


def test_recovery_days_recovered():
    # trough 90 at idx 3, back above prior peak (110) at idx 4 → 1 day
    assert recovery_days([100, 110, 105, 90, 110]) == 1


def test_recovery_days_not_recovered():
    assert recovery_days([100, 110, 105, 90, 95]) is None


def test_beta_alpha_exact_relationship():
    b = [0.01, -0.02, 0.03]
    f = [0.015, -0.03, 0.045]  # f = 1.5 * b exactly
    beta, alpha = beta_alpha(f, b)
    assert beta is not None and abs(beta - 1.5) < 1e-9
    assert alpha is not None and abs(alpha) < 1e-9


def test_beta_alpha_too_short():
    assert beta_alpha([0.01], [0.01]) == (None, None)
