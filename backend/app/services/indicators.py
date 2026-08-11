"""Financial technical indicators (pure standard library).

Provides:
- sma: Simple Moving Average
- max_drawdown: Maximum drawdown of a price/value series
"""
from __future__ import annotations


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