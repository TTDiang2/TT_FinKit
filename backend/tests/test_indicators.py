"""Tests for indicators module (SMA + Max Drawdown)."""
from app.services.indicators import sma, max_drawdown


# ---------- SMA tests ----------

def test_sma_basic():
    """SMA with window=3 on [1,2,3,4,5]: first 2 are None, then means."""
    result = sma([1, 2, 3, 4, 5], 3)
    assert result == [None, None, 2.0, 3.0, 4.0]


def test_sma_empty_series():
    """SMA on empty series returns empty list."""
    assert sma([], 3) == []


def test_sma_window_larger_than_series():
    """SMA when window > len(series): all positions are None."""
    assert sma([1, 2], 5) == [None, None]


def test_sma_window_equals_one():
    """SMA with window=1: every value is itself (as float)."""
    assert sma([1, 2, 3], 1) == [1.0, 2.0, 3.0]


def test_sma_window_equals_length():
    """SMA with window == len(series): only last position has the mean."""
    assert sma([1.0, 2.0, 3.0, 4.0], 4) == [None, None, None, 2.5]


def test_sma_floats():
    """SMA works with float inputs."""
    result = sma([1.5, 2.5, 3.5, 4.5], 2)
    assert result == [None, 3.0, 4.5, 6.0] or result[0] is None
    # Check each value
    assert result[0] is None
    assert abs(result[1] - 2.0) < 1e-9   # (1.5+2.5)/2
    assert abs(result[2] - 3.0) < 1e-9   # (2.5+3.5)/2
    assert abs(result[3] - 4.0) < 1e-9   # (3.5+4.5)/2


def test_sma_output_length_matches_input():
    """Output length always equals input length."""
    for data, w in [([1, 2, 3], 3), ([1], 1), ([1, 2, 3, 4, 5], 10)]:
        assert len(sma(data, w)) == len(data)


# ---------- Max Drawdown tests ----------

def test_max_drawdown_basic():
    """Peak 12, trough 8 -> drawdown = (8-12)/12 = -0.3333..."""
    result = max_drawdown([10, 12, 8, 11, 9])
    assert abs(result - (-1 / 3)) < 1e-9
    # Also check ~ -0.3333 rounded
    assert round(result, 4) == -0.3333


def test_max_drawdown_monotonic_up():
    """Monotonically increasing series -> 0.0 (no drawdown)."""
    assert max_drawdown([1, 2, 3, 4, 5]) == 0.0


def test_max_drawdown_monotonic_down():
    """Monotonically decreasing series -> (1-5)/5 = -0.8."""
    assert max_drawdown([5, 4, 3, 2, 1]) == -0.8


def test_max_drawdown_empty():
    """Empty series -> 0.0."""
    assert max_drawdown([]) == 0.0


def test_max_drawdown_single_point():
    """Single point -> 0.0 (no drawdown possible)."""
    assert max_drawdown([7]) == 0.0


def test_max_drawdown_never_positive():
    """Drawdown is always <= 0."""
    samples = [
        [10, 12, 8, 11, 9],
        [5, 4, 3, 2, 1],
        [1, 1, 1, 1],
        [100, 50, 75, 25, 200],  # big drawdown then new high
    ]
    for s in samples:
        assert max_drawdown(s) <= 0.0


def test_max_drawdown_recovery_to_new_peak():
    """max_drawdown returns the worst (most negative) drawdown observed,
    even if the series later recovers to a new peak."""
    # Peak 100 -> trough 25 = -0.75; recovery to 200 doesn't erase that.
    series = [100, 50, 25, 75, 200]
    assert max_drawdown(series) == -0.75


def test_max_drawdown_deep_then_partial_recovery():
    """Drawdown measures worst peak-to-trough across whole series."""
    series = [10, 20, 15, 5, 8, 12]
    # Peak 20 -> trough 5 = -0.75
    assert max_drawdown(series) == -0.75


def test_max_drawdown_float_values():
    """Works with float inputs."""
    series = [1.0, 2.0, 0.5, 1.5]
    # Peak 2.0, trough 0.5 -> (0.5-2.0)/2.0 = -0.75
    assert max_drawdown(series) == -0.75