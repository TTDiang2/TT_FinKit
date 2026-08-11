"""Lightweight in-place column migrations for SQLite.

SQLAlchemy's `Base.metadata.create_all` only creates missing *tables* — it
won't add columns to existing tables. We add a small, idempotent migration
step here so existing `finkit.db` files pick up new columns without needing
Alembic or a wipe.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def _existing_columns(conn: AsyncConnection, table: str) -> set[str]:
    rows = await conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in rows.fetchall()}


async def _add_column_if_missing(conn: AsyncConnection, table: str, column: str, ddl: str) -> None:
    cols = await _existing_columns(conn, table)
    if column not in cols:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def run_lightweight_migrations(conn: AsyncConnection) -> None:
    """Add new columns introduced after the initial release to existing tables."""
    # investments: new market identifiers + price bookkeeping
    await _add_column_if_missing(conn, "investments", "symbol", "VARCHAR DEFAULT '' NOT NULL")
    await _add_column_if_missing(conn, "investments", "exchange", "VARCHAR DEFAULT '' NOT NULL")
    await _add_column_if_missing(conn, "investments", "last_price_update", "DATETIME")

    # user_settings: AI investment analysis knobs
    await _add_column_if_missing(conn, "user_settings", "ai_search_backend", "VARCHAR DEFAULT 'duckduckgo'")
    await _add_column_if_missing(conn, "user_settings", "ai_search_api_key", "VARCHAR DEFAULT ''")
    await _add_column_if_missing(conn, "user_settings", "ai_investment_preset_id", "VARCHAR")
