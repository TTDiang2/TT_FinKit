"""Strategy management service."""
import ast, json
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.strategy import Strategy

def validate_strategy_code(code: str) -> tuple[bool, str]:
    """Check that code contains a Strategy subclass with required metadata."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "Strategy":
                    # Check required attribute 'name' exists
                    found_attrs = set()
                    for item in node.body:
                        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            found_attrs.add(item.target.id)
                        elif isinstance(item, ast.Assign):
                            for t in item.targets:
                                if isinstance(t, ast.Name):
                                    found_attrs.add(t.id)
                    if "name" not in found_attrs:
                        return False, f"Strategy subclass '{node.name}' missing required attribute 'name'"
                    found = True
                    break
    if not found:
        return False, "No Strategy subclass found. Must inherit from Strategy."
    return True, "OK"

async def list_strategies(
    db: AsyncSession,
    folder: str | None = None,
    sort: str = "created_at_desc",
) -> list[Strategy]:
    """List all strategy versions.

    - folder: Optional exact-match filter (None = no filter)
    - sort: "created_at_asc" | "created_at_desc" (default desc) — applied
      BEFORE the dedup-by-name-keep-latest-version step in the router.
    """
    stmt = select(Strategy)
    if folder is not None:
        stmt = stmt.where(Strategy.folder == folder)
    if sort == "created_at_asc":
        stmt = stmt.order_by(Strategy.created_at.asc(), Strategy.name)
    else:
        stmt = stmt.order_by(Strategy.created_at.desc(), Strategy.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def get_strategy(db: AsyncSession, strategy_id: str, version: int | None = None) -> Strategy | None:
    if version:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.version == version)
        )
    else:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id).order_by(desc(Strategy.version))
        )
    return result.scalar_one_or_none()

async def import_strategy(
    db: AsyncSession, name: str, code: str, description: str = "",
    params_schema: dict = {}, rebalance_freq: str = "monthly",
    folder: str = "", factor_keys: list[str] | None = None,
    source_file: str | None = None,
) -> tuple[Strategy, str]:
    """Import or update a strategy. If name exists, bump version. Returns (strategy, status)."""
    # factor_keys 存 Text 列必须 json.dumps（空列表存 None）
    factor_keys_json = json.dumps(list(factor_keys), ensure_ascii=False) if factor_keys else None

    # Check for existing strategy with same name (get latest version)
    result = await db.execute(
        select(Strategy).where(Strategy.name == name).order_by(desc(Strategy.version))
    )
    existing = result.scalar_one_or_none()

    if existing:
        new_version = existing.version + 1
        strategy = Strategy(
            name=name, code=code, description=description,
            version=new_version, params_schema=json.dumps(params_schema),
            rebalance_freq=rebalance_freq, is_builtin=False,
            folder=folder, factor_keys=factor_keys_json, source_file=source_file,
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        return strategy, "updated"
    else:
        strategy = Strategy(
            name=name, code=code, description=description,
            version=1, params_schema=json.dumps(params_schema),
            rebalance_freq=rebalance_freq, is_builtin=False,
            folder=folder, factor_keys=factor_keys_json, source_file=source_file,
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        return strategy, "imported"

async def delete_strategy_version(db: AsyncSession, strategy_id: str, version: int) -> bool:
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.version == version)
    )
    strat = result.scalar_one_or_none()
    if not strat or strat.is_builtin:
        return False
    await db.delete(strat)
    await db.commit()
    return True
