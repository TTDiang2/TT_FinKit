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

    # investments: money-market fund flags (P5)
    await _add_column_if_missing(conn, "investments", "is_money_market", "BOOLEAN DEFAULT 0")
    await _add_column_if_missing(conn, "investments", "seven_day_yield", "FLOAT")

    # user_settings: AI investment analysis knobs
    await _add_column_if_missing(conn, "user_settings", "ai_search_backend", "VARCHAR DEFAULT 'duckduckgo'")
    await _add_column_if_missing(conn, "user_settings", "ai_search_api_key", "VARCHAR DEFAULT ''")
    await _add_column_if_missing(conn, "user_settings", "ai_investment_preset_id", "VARCHAR")

    # accounts: reconciliation mode (direct vs composite bank-statement mapping)
    await _add_column_if_missing(conn, "accounts", "bank_statement_mode", "VARCHAR DEFAULT 'direct' NOT NULL")
    # accounts: free-form reconciliation formula (JSON); backfill preset by legacy mode
    await _add_column_if_missing(conn, "accounts", "bank_formula", "TEXT")
    await conn.execute(
        text(
            "UPDATE accounts SET bank_formula = CASE bank_statement_mode "
            "WHEN 'composite' THEN '{\"income\": [\"transfer_in\", \"refund\", \"income\"], \"expense\": [\"expense_positive\"]}' "
            "ELSE '{\"income\": [\"income\"], \"expense\": [\"expense_net\"]}' END "
            "WHERE bank_formula IS NULL"
        )
    )

    # transactions: 交易地点/附言（银行流水原始字段）
    await _add_column_if_missing(conn, "transactions", "location", "VARCHAR DEFAULT '' NOT NULL")

    # investment_transactions: per-transaction fee (cost, counts into diluted cost basis)
    await _add_column_if_missing(conn, "investment_transactions", "fee", "FLOAT DEFAULT 0 NOT NULL")
