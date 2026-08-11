"""Fund asset_class classification and default benchmark lookup.

Pure-stdlib module — no DB, async, iFinD, or network. Used by FinKit's
investment tab to normalize a fund's underlying_asset_type (or name) into a
canonical asset_class bucket, and to look up a default benchmark (symbol,
exchange) for that bucket.

Classification rule:
  1. If underlying_asset_type is set, try exact match against known types
     ("黄金" / "原油" / "美股" / "股票" → "A股" / "债券" / "油气" / "货币").
  2. Otherwise, fall back to keyword inclusion on the fund name.
     Order matters: "油气" must be checked AFTER "原油" / "石油" so that
     "诺安油气能源" doesn't get mis-bucketed as 原油.

Default benchmarks:
  黄金  → 沪金主力 AU8888.SH (SH)
  原油  → 待命门确认 (empty)
  美股  → 纳斯达克综指 .IXIC (US)
  A股   → 沪深300    000300.SH (SH)
  其余  → (empty, empty)
"""
from __future__ import annotations

# Exact-match table for underlying_asset_type → canonical asset_class.
# "股票" maps to "A股" because FinKit users hold domestic open-ended equity
# funds (e.g. 易方达平稳 110001, 富国通胀 100039).
_EXACT_TYPE_MAP: dict[str, str] = {
    "黄金": "黄金",
    "原油": "原油",
    "美股": "美股",
    "股票": "A股",
    "债券": "债券",
    "油气": "油气",
    "货币": "货币",
}

# Keyword → asset_class, evaluated in order on the fund name. Order matters:
# "油气" is checked AFTER "石油" / "原油" so a fund named "诺安油气能源" is
# not mis-classified as 原油.
_NAME_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("黄金", "黄金"),
    ("石油", "原油"),
    ("原油", "原油"),
    ("油气", "油气"),
    ("纳斯达克", "美股"),
    ("美股", "美股"),
    ("标普", "美股"),
    ("债券", "债券"),
)


def classify_asset_class(underlying_asset_type: str, name: str) -> str:
    """Normalize a fund's asset_class from underlying type or name.

    Args:
        underlying_asset_type: DB-stored canonical type ("黄金", "原油", ...);
            empty string if unset.
        name: fund display name, used for keyword fallback when underlying
            is empty or unrecognized.

    Returns:
        Canonical asset_class bucket. Falls through to "其他" if nothing
        matches.
    """
    # Step 1: exact match on underlying_asset_type.
    t = (underlying_asset_type or "").strip()
    if t and t in _EXACT_TYPE_MAP:
        return _EXACT_TYPE_MAP[t]

    # Step 2: keyword inclusion on name (ordered; first hit wins).
    n = name or ""
    for kw, bucket in _NAME_KEYWORDS:
        if kw in n:
            return bucket

    return "其他"


# (symbol, exchange) per asset_class. Symbol "" / exchange "" means
# no default benchmark is configured (caller must fall back to user choice
# or skip the benchmark overlay).
_BENCHMARK_MAP: dict[str, tuple[str, str]] = {
    "黄金": ("AU8888.SH", "SH"),
    "美股": (".IXIC", "US"),
    "A股": ("000300.SH", "SH"),
}


def default_benchmark(asset_class: str) -> tuple[str, str]:
    """Look up default benchmark (symbol, exchange) for an asset_class.

    Args:
        asset_class: canonical bucket from classify_asset_class.

    Returns:
        (symbol, exchange) tuple. ("", "") for unconfigured classes
        (原油 / 油气 / 债券 / 货币 / 其他).
    """
    return _BENCHMARK_MAP.get(asset_class, ("", ""))