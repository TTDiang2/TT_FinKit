"""Marker that this module is side-effect: it walks Base.metadata and tags
public tables. Imported from app.main on_startup after all model modules are
loaded so every class is registered.

Add new public models by appending their table name to PUBLIC_TABLE_NAMES.
"""
from __future__ import annotations

PUBLIC_TABLE_NAMES: set[str] = {
    "research_assets",
    "research_prices",
    "research_groups",
    "research_group_members",
    "research_asset_stats",
    "research_asset_holdings",
    "strategies",
    "factors",
    "factor_values",
    "factor_exposures",
    "factor_ic_points",
    "factor_evaluations",
}


def _mark_public_tables() -> int:
    """Walk Base.metadata and set Table.info['public'] = True on public tables.
    Idempotent (overwrites). Returns number of tables marked.
    """
    # Local import to avoid circular: app.database imports nothing from models.
    from app.database import Base
    n = 0
    for t in Base.metadata.sorted_tables:
        if t.name in PUBLIC_TABLE_NAMES:
            t.info["public"] = True
            n += 1
        else:
            t.info["public"] = False
    return n