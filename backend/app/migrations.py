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


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    rows = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    )
    return rows.fetchone() is not None


async def _add_column_if_missing(conn: AsyncConnection, table: str, column: str, ddl: str) -> None:
    if not await _table_exists(conn, table):
        return
    cols = await _existing_columns(conn, table)
    if column not in cols:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    rows = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table"),
        {"table": table},
    )
    return rows.fetchone() is not None


async def add_tablemigration(conn: AsyncConnection, table: str, ddl: str) -> None:
    """Create a brand-new table if it does not already exist (idempotent).

    New tables are normally handled by ``Base.metadata.create_all`` on startup;
    this helper exists so mid-cycle tables can be created explicitly (e.g. in
    deployments where the model module may not be imported yet). ``ddl`` is the
    full ``CREATE TABLE ...`` statement.
    """
    if not await _table_exists(conn, table):
        await conn.execute(text(ddl))


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

    # user_settings: Phase 6 monitor alert thresholds (JSON blob, §4.9)
    await _add_column_if_missing(conn, "user_settings", "monitor_thresholds", "TEXT")

    # strategies: single-activation for the live signal engine
    await _add_column_if_missing(conn, "strategies", "activated_at", "DATETIME")
    # strategies: author-declared semantic version + full docstring logic body
    await _add_column_if_missing(conn, "strategies", "version_note", "VARCHAR")
    await _add_column_if_missing(conn, "strategies", "logic", "TEXT")

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

    # research_assets: purchase quota + multi-dimension auto classification
    await _add_column_if_missing(conn, "research_assets", "purchase_limit", "FLOAT")
    await _add_column_if_missing(conn, "research_assets", "fund_kind", "VARCHAR DEFAULT '' NOT NULL")
    await _add_column_if_missing(conn, "research_assets", "asset_class", "VARCHAR DEFAULT '' NOT NULL")
    await _add_column_if_missing(conn, "research_assets", "region", "VARCHAR DEFAULT '' NOT NULL")
    await _add_column_if_missing(conn, "research_assets", "auto_tags", "TEXT DEFAULT '[]' NOT NULL")
    await _add_column_if_missing(conn, "research_assets", "profile_synced_at", "DATETIME")

    # investment_transactions: per-transaction fee (cost, counts into diluted cost basis)
    await _add_column_if_missing(conn, "investment_transactions", "fee", "FLOAT DEFAULT 0 NOT NULL")

    # backtests (Phase 4): safety net for DBs created during partial rollout
    await _add_column_if_missing(conn, "backtests", "results", "TEXT")
    await _add_column_if_missing(conn, "backtests", "error", "TEXT")

    # signals: Phase 5 signal table (strategy output snapshots)
    await add_tablemigration(
        conn, "signals",
        """
        CREATE TABLE IF NOT EXISTS signals (
            id VARCHAR PRIMARY KEY,
            strategy_id VARCHAR NOT NULL,
            strategy_version INTEGER NOT NULL,
            run_date VARCHAR NOT NULL,
            as_of_date VARCHAR NOT NULL,
            next_rebalance_date VARCHAR,
            target_weights TEXT NOT NULL,
            risk_status TEXT,
            backtest_id VARCHAR,
            created_at DATETIME
        )
        """,
    )
