"""Tests for Phase P4 strategy upgrades: docstring parsing, import metadata
persistence, import-folder, move-all-versions, and list sort/folder filtering.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import Base
from app.models.strategy import Strategy
from app.models.backtest import Backtest
from app.services.strategy_meta import parse_strategy_docstring
from app.services.strategy_service import import_strategy
from app.routers.strategies import (
    import_strategy_endpoint,
    parse_docstring_endpoint,
    import_folder_endpoint,
    move_strategy_endpoint,
    list_strategies_endpoint,
)
from app.schemas.strategy import StrategyCreate, StrategyParseRequest, StrategyMoveRequest


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


FULL_DOCSTRING = '''\
"""
name: 黄金双均线择时
description: 快慢均线金叉持有/死叉空仓
rebalance_freq: daily
factor_keys: [gold, equity]
version_note: v2 增加黄金因子确认
---
以下是自由文档，导入时忽略
"""
class MyStrategy: pass
'''

VALID_CODE = '''\
"""name: 黄金双均线择时
description: 快慢均线金叉持有/死叉空仓
rebalance_freq: daily
factor_keys: [gold]
---
"""
from finkit_strategy import Strategy

class MyStrategy(Strategy):
    name = "黄金双均线择时"
    description = ""
    rebalance_freq = "daily"
    params_schema = {}
'''

GOOD_FILE_CODE = '''\
"""name: 文件夹策略甲
rebalance_freq: weekly
factor_keys: [gold]
---
"""
from finkit_strategy import Strategy

class FolderStrat(Strategy):
    name = "文件夹策略甲"
    description = ""
    rebalance_freq = "weekly"
    params_schema = {}
'''


class TestParseStrategyDocstring:
    def test_full_valid_docstring(self):
        meta = parse_strategy_docstring(FULL_DOCSTRING)
        assert meta["name"] == "黄金双均线择时"
        assert meta["description"] == "快慢均线金叉持有/死叉空仓"
        assert meta["rebalance_freq"] == "daily"
        assert meta["factor_keys"] == ["gold", "equity"]
        assert meta["version_note"] == "v2 增加黄金因子确认"

    def test_missing_fields_return_none(self):
        code = '''\
"""name: 只有名字
"""
class MyStrategy: pass
'''
        meta = parse_strategy_docstring(code)
        assert meta["name"] == "只有名字"
        assert meta["description"] is None
        assert meta["rebalance_freq"] is None
        assert meta["factor_keys"] is None
        assert meta["version_note"] is None

    def test_no_docstring(self):
        meta = parse_strategy_docstring("x = 1\n")
        assert meta["name"] is None
        assert meta["factor_keys"] is None
        assert meta["description"] is None

    def test_bad_syntax_no_crash(self):
        meta = parse_strategy_docstring("def broken(:")
        assert meta["name"] is None
        assert meta["factor_keys"] is None

    def test_factor_keys_bracket_form(self):
        code = '"""\nfactor_keys: [gold, equity, size]\n"""\nx=1'
        meta = parse_strategy_docstring(code)
        assert meta["factor_keys"] == ["gold", "equity", "size"]

    def test_factor_keys_comma_form(self):
        code = '"""\nfactor_keys: gold,equity\n"""\nx=1'
        meta = parse_strategy_docstring(code)
        assert meta["factor_keys"] == ["gold", "equity"]

    def test_separator_honored(self):
        # --- 分隔行之后的键不能被解析进元数据
        code = '''\
"""name: 头部策略
foo: bar
---
name: 尾部覆盖
"""
class MyStrategy: pass
'''
        meta = parse_strategy_docstring(code)
        assert meta["name"] == "头部策略"
        assert "尾部覆盖" not in meta["name"]


class TestImportEndpoint:
    def test_import_persists_folder_factor_keys_source_file(self):
        async def inner():
            db, engine = await _make_db()
            try:
                req = StrategyCreate(
                    name="", code=VALID_CODE, description="", params_schema={},
                    rebalance_freq="", folder="量化", source_file="doc_strat.py",
                    factor_keys=["equity"],
                )
                result = await import_strategy_endpoint(req, db)
                row = (await db.execute(
                    select(Strategy).where(Strategy.id == result.strategy_id)
                )).scalar_one()
                assert row.folder == "量化"
                assert row.source_file == "doc_strat.py"
                # 表单 ["equity"] 与 docstring ["gold"] 取并集去重
                assert json.loads(row.factor_keys) == ["equity", "gold"]
                # 表单空值回退 docstring
                assert row.name == "黄金双均线择时"
                assert row.description == "快慢均线金叉持有/死叉空仓"
                assert row.rebalance_freq == "daily"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_import_form_field_wins_when_non_empty(self):
        async def inner():
            db, engine = await _make_db()
            try:
                req = StrategyCreate(
                    name="表单名", code=VALID_CODE, description="表单描述",
                    params_schema={}, rebalance_freq="monthly",
                    folder="", source_file=None, factor_keys=None,
                )
                result = await import_strategy_endpoint(req, db)
                row = (await db.execute(
                    select(Strategy).where(Strategy.id == result.strategy_id)
                )).scalar_one()
                assert row.name == "表单名"
                assert row.description == "表单描述"
                assert row.rebalance_freq == "monthly"
                assert json.loads(row.factor_keys) == ["gold"]
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_parse_docstring_endpoint(self):
        async def inner():
            resp = await parse_docstring_endpoint(StrategyParseRequest(code=FULL_DOCSTRING))
            assert resp["name"] == "黄金双均线择时"
            assert resp["factor_keys"] == ["gold", "equity"]
            assert resp["rebalance_freq"] == "daily"
        asyncio.run(inner())


class TestImportFolder:
    def test_import_folder_happy_path(self, monkeypatch, tmp_path):
        async def inner():
            strategies_dir = tmp_path / "folder_strategies"
            strategies_dir.mkdir()
            (strategies_dir / "good_strat.py").write_text(GOOD_FILE_CODE, encoding="utf-8")
            (strategies_dir / "broken_strat.py").write_text("def broken(:", encoding="utf-8")
            monkeypatch.setattr("app.routers.strategies.STRATEGIES_DIR", strategies_dir)

            db, engine = await _make_db()
            try:
                resp = await import_folder_endpoint(db)
                assert len(resp["imported"]) == 1
                assert resp["imported"][0]["file"] == "good_strat.py"
                assert resp["imported"][0]["name"] == "文件夹策略甲"
                assert resp["errors"][0]["file"] == "broken_strat.py"
                rows = (await db.execute(select(Strategy))).scalars().all()
                assert len(rows) == 1
                row = rows[0]
                assert row.source_file == "good_strat.py"
                assert row.folder == ""
                assert json.loads(row.factor_keys) == ["gold"]
                assert row.rebalance_freq == "weekly"
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_import_folder_missing_dir_creates_it(self, monkeypatch, tmp_path):
        async def inner():
            strategies_dir = tmp_path / "never_exists"
            monkeypatch.setattr("app.routers.strategies.STRATEGIES_DIR", strategies_dir)
            db, engine = await _make_db()
            try:
                resp = await import_folder_endpoint(db)
                assert resp == {"imported": [], "errors": []}
                assert strategies_dir.is_dir()
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestMoveEndpoint:
    def test_move_updates_all_versions_by_name(self):
        async def inner():
            db, engine = await _make_db()
            try:
                s1, _ = await import_strategy(
                    db, name="MoveMe", code=VALID_CODE, description="",
                    params_schema={}, rebalance_freq="monthly",
                )
                s2, _ = await import_strategy(
                    db, name="MoveMe", code=VALID_CODE, description="",
                    params_schema={}, rebalance_freq="monthly",
                )
                assert s2.version == 2
                resp = await move_strategy_endpoint(
                    s2.id, StrategyMoveRequest(folder="__archive__"), db
                )
                assert resp.folder == "__archive__"
                rows = (await db.execute(
                    select(Strategy).where(Strategy.name == "MoveMe")
                )).scalars().all()
                assert len(rows) == 2
                assert all(r.folder == "__archive__" for r in rows)
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_move_unknown_strategy_404(self):
        async def inner():
            db, engine = await _make_db()
            try:
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await move_strategy_endpoint(
                        "nope", StrategyMoveRequest(folder="量化"), db
                    )
                assert exc_info.value.status_code == 404
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


class TestListEndpoint:
    def _seed(self, db, rows: list[dict]):
        for r in rows:
            db.add(Strategy(
                id=r["id"], name=r["name"], code="x", version=r.get("version", 1),
                params_schema="{}", rebalance_freq="monthly",
                folder=r.get("folder", ""), created_at=r["created_at"],
            ))
        return db

    def test_list_sort_param_order(self):
        async def inner():
            db, engine = await _make_db()
            try:
                base = datetime.utcnow()
                self._seed(db, [
                    {"id": "a", "name": "Alpha", "created_at": base - timedelta(days=2)},
                    {"id": "b", "name": "Beta", "created_at": base - timedelta(days=1)},
                    {"id": "c", "name": "Gamma", "created_at": base},
                ])
                await db.commit()

                resp_desc = await list_strategies_endpoint(folder=None, sort="created_at_desc", db=db)
                assert [s.name for s in resp_desc] == ["Gamma", "Beta", "Alpha"]

                resp_asc = await list_strategies_endpoint(folder=None, sort="created_at_asc", db=db)
                assert [s.name for s in resp_asc] == ["Alpha", "Beta", "Gamma"]
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_list_folder_filter_and_dedup_keeps_latest_version(self):
        async def inner():
            db, engine = await _make_db()
            try:
                base = datetime.utcnow()
                self._seed(db, [
                    {"id": "x1", "name": "X", "version": 1, "created_at": base - timedelta(days=2)},
                    {"id": "x2", "name": "X", "version": 2, "created_at": base - timedelta(days=1)},
                    {"id": "y1", "name": "Y", "folder": "量化", "created_at": base},
                ])
                await db.commit()

                resp = await list_strategies_endpoint(folder=None, sort="created_at_desc", db=db)
                names = [s.name for s in resp]
                assert names == ["Y", "X"]
                # 去重后保最新版本
                x_row = next(s for s in resp if s.name == "X")
                assert x_row.version == 2

                resp_q = await list_strategies_endpoint(folder="量化", sort="created_at_desc", db=db)
                assert [s.name for s in resp_q] == ["Y"]
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_latest_backtest_attached(self):
        async def inner():
            db, engine = await _make_db()
            try:
                base = datetime.utcnow()
                req = StrategyCreate(name="BT", code=VALID_CODE)
                result = await import_strategy_endpoint(req, db)
                sid = result.strategy_id
                # 先建一条 done 回测，再建一条更新的 failed 回测（不应覆盖 done 的展示）
                db.add(Backtest(
                    id="bt-done", strategy_id=sid, strategy_version=1,
                    start_date="2025-01-01", end_date="2025-01-31",
                    rebalance_freq="monthly", data_as_of="2025-01-31",
                    status="done", results=json.dumps({"metrics": {
                        "ann_return": 0.164, "ann_volatility": 0.12,
                        "sharpe": 0.66, "max_drawdown": -0.251,
                    }}),
                    created_at=base + timedelta(hours=1),
                ))
                db.add(Backtest(
                    id="bt-failed", strategy_id=sid, strategy_version=1,
                    start_date="2025-01-01", end_date="2025-02-01",
                    rebalance_freq="monthly", data_as_of="2025-02-01",
                    status="failed", results=json.dumps({"metrics": {"ann_return": 9.9}}),
                    created_at=base + timedelta(hours=2),
                ))
                await db.commit()

                resp = await list_strategies_endpoint(folder=None, sort="created_at_desc", db=db)
                assert len(resp) == 1
                lb = resp[0].latest_backtest
                assert lb is not None
                assert lb["id"] == "bt-done"
                assert abs(lb["ann_return"] - 0.164) < 1e-9
                assert abs(lb["ann_volatility"] - 0.12) < 1e-9
                assert abs(lb["sharpe"] - 0.66) < 1e-9
                assert abs(lb["max_drawdown"] - (-0.251)) < 1e-9
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())

    def test_list_no_backtest_returns_none(self):
        async def inner():
            db, engine = await _make_db()
            try:
                base = datetime.utcnow()
                self._seed(db, [{"id": "n1", "name": "NoBT", "created_at": base}])
                await db.commit()
                resp = await list_strategies_endpoint(db=db)
                assert resp[0].latest_backtest is None
                assert resp[0].factor_keys == []
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())
