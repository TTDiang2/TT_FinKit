"""Financial technical indicators (pure standard library).

Provides:
- sma: Simple Moving Average
- max_drawdown: Maximum drawdown of a price/value series
- annualized_return / annualized_volatility / sharpe_ratio
"""
from __future__ import annotations

TRADING_DAYS_PER_YEAR = 252


def sma(series: list[float], window: int) -> list[float | None]:
    """Simple Moving Average.

    Output length equals input length. The first ``window - 1`` positions are
    ``None`` (insufficient data to form a full window). From position
    ``window - 1`` onward, each position holds the arithmetic mean of the
    current value and the preceding ``window - 1`` values.

    Args:
        series: Input numeric sequence (ints are coerced to floats).
        window: Window size. If ``window <= 0`` or empty series, behavior is
            as documented (all ``None`` for invalid window, empty list for
            empty series).

    Returns:
        A list of the same length as ``series``. Each element is either a
        ``float`` (the rolling mean) or ``None`` (insufficient data).
    """
    n = len(series)
    if n == 0:
        return []
    if window <= 0:
        return [None] * n

    result: list[float | None] = [None] * n

    # Initial window sum
    if window <= n:
        running_sum = 0.0
        for i in range(window):
            running_sum += series[i]
        result[window - 1] = running_sum / window
        # Roll forward
        for i in range(window, n):
            running_sum += series[i] - series[i - window]
            result[i] = running_sum / window
    # else: window > n -> all None already

    return result


def max_drawdown(series: list[float]) -> float:
    """Maximum drawdown of a value series.

    Tracks the running peak from the start of the series and returns the
    minimum (most negative) value of ``(current - peak) / peak`` observed
    over the whole series.

    Args:
        series: Input numeric sequence (e.g. NAV, prices).

    Returns:
        A float in (-inf, 0]. ``0.0`` means no drawdown (monotonically
        non-decreasing series, or empty / single-point series). Negative
        values represent fractional loss from peak (e.g. ``-0.25`` = 25%
        drawdown).
    """
    n = len(series)
    if n <= 1:
        return 0.0

    peak = series[0]
    max_dd = 0.0
    for value in series:
        if value > peak:
            peak = value
        if peak != 0:
            dd = (value - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd


def daily_returns(series: list[float]) -> list[float]:
    return [
        series[i] / series[i - 1] - 1.0
        for i in range(1, len(series))
        if series[i - 1] != 0
    ]


def annualized_return(series: list[float], periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float | None:
    if len(series) < 2 or series[0] <= 0 or series[-1] <= 0:
        return None
    years = (len(series) - 1) / periods_per_year
    if years <= 0:
        return None
    return (series[-1] / series[0]) ** (1.0 / years) - 1.0


def annualized_volatility(series: list[float], periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float | None:
    rets = daily_returns(series)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return var ** 0.5 * periods_per_year ** 0.5


def sharpe_ratio(
    series: list[float],
    risk_free_annual: float = 0.02,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float | None:
    ann = annualized_return(series, periods_per_year)
    vol = annualized_volatility(series, periods_per_year)
    if ann is None or vol is None or vol <= 0:
        return None
    return (ann - risk_free_annual) / vol


def downside_deviation(series: list[float], periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float | None:
    """Annualized downside deviation: std of negative daily returns only."""
    rets = [r for r in daily_returns(series) if r < 0]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return var ** 0.5 * periods_per_year ** 0.5


def sortino_ratio(
    series: list[float],
    risk_free_annual: float = 0.02,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float | None:
    ann = annualized_return(series, periods_per_year)
    dd = downside_deviation(series, periods_per_year)
    if ann is None or dd is None or dd <= 0:
        return None
    return (ann - risk_free_annual) / dd


def calmar_ratio(series: list[float], periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float | None:
    """Annualized return divided by |max drawdown|."""
    ann = annualized_return(series, periods_per_year)
    mdd = max_drawdown(series)
    if ann is None or mdd >= 0:
        return None
    return ann / abs(mdd)


def max_drawdown_duration(series: list[float]) -> int:
    """Trading days from the running peak to the deepest trough."""
    if len(series) < 2:
        return 0
    peak = series[0]
    peak_idx = 0
    deepest = 0.0
    trough_idx = 0
    trough_peak_idx = 0
    for i, v in enumerate(series):
        if v > peak:
            peak = v
            peak_idx = i
        elif peak != 0:
            dd = (v - peak) / peak
            if dd < deepest:
                deepest = dd
                trough_idx = i
                trough_peak_idx = peak_idx
    return max(0, trough_idx - trough_peak_idx)


def recovery_days(series: list[float]) -> int | None:
    """Trading days from the deepest trough back above the prior peak; None if not recovered yet."""
    if len(series) < 2:
        return None
    peak = series[0]
    peak_idx = 0
    deepest = 0.0
    trough_idx = 0
    trough_peak = peak
    for i, v in enumerate(series):
        if v > peak:
            peak = v
            peak_idx = i
        elif peak != 0:
            dd = (v - peak) / peak
            if dd < deepest:
                deepest = dd
                trough_idx = i
                trough_peak = peak
    if deepest >= 0:
        return None
    for i in range(trough_idx + 1, len(series)):
        if series[i] >= trough_peak:
            return i - trough_idx
    return None


def beta_alpha(
    fund_returns: list[float],
    benchmark_returns: list[float],
) -> tuple[float | None, float | None]:
    """OLS beta and annualized alpha from aligned daily return pairs."""
    n = len(fund_returns)
    if n < 2 or len(benchmark_returns) != n:
        return None, None
    f_mean = sum(fund_returns) / n
    b_mean = sum(benchmark_returns) / n
    cov = sum((f - f_mean) * (b - b_mean) for f, b in zip(fund_returns, benchmark_returns)) / (n - 1)
    var = sum((b - b_mean) ** 2 for b in benchmark_returns) / (n - 1)
    if var <= 0:
        return None, None
    beta = cov / var
    alpha = (f_mean - beta * b_mean) * TRADING_DAYS_PER_YEAR
    return beta, alpha