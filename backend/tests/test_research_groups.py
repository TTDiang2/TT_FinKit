"""Research group CRUD tests + C-share fee html parsing regression.

Groups: create (ownership-filtered members, dup-name 409), update (rename +
full member replace), delete. Fee parse: 天天基金 C 类页式（无「前端」标题、
区间中间档、卖出确认日 T+N）— uses recorded markup shapes, no network.
"""
import asyncio
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base
from app.models.user import User
from app.models.research_asset import ResearchAsset
from app.models.research_group import ResearchGroup, ResearchGroupMember
from app.routers import research_assets as ra
from app.services.fund_profile import parse_fee_html


async def _make_db() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker(), engine


class TestGroups:
    def test_create_update_delete(self):
        async def inner():
            db, engine = await _make_db()
            try:
                u = User(email="g@t.co", password_hash="x")
                other = User(email="o@t.co", password_hash="x")
                db.add_all([u, other])
                await db.flush()
                a1 = ResearchAsset(user_id=u.id, symbol="A1", exchange="FUND_CN",
                                   name="基金A1", asset_type="fund")
                a2 = ResearchAsset(user_id=u.id, symbol="A2", exchange="FUND_CN",
                                   name="基金A2", asset_type="fund")
                alien = ResearchAsset(user_id=other.id, symbol="ZZ", exchange="FUND_CN",
                                      name="别人家的", asset_type="fund")
                db.add_all([a1, a2, alien])
                await db.commit()

                g = await ra.create_group(
                    ra.ResearchGroupCreate(name="全宽基", asset_ids=[a1.id, a2.id, alien.id]),
                    user_id=u.id, db=db)
                assert g.name == "全宽基"
                # 共享模式（2026-09-02）：public 标的全局可见，不再按 user 过滤成员
                assert sorted(g.asset_ids) == sorted([a1.id, a2.id, alien.id])

                try:
                    await ra.create_group(ra.ResearchGroupCreate(name="全宽基"),
                                          user_id=u.id, db=db)
                    assert False, "should 409"
                except Exception as e:
                    assert getattr(e, "status_code", None) == 409

                g2 = await ra.update_group(
                    g.id, ra.ResearchGroupUpdate(name="大类资产", asset_ids=[a1.id]),
                    user_id=u.id, db=db)
                assert g2.name == "大类资产" and g2.asset_ids == [a1.id]

                mine = await ra.list_groups(user_id=u.id, db=db)
                theirs = await ra.list_groups(user_id=other.id, db=db)
                # 共享模式：组合全局可见，两个账号都能看到同一组
                assert len(mine) == 1 and len(theirs) == 1

                await ra.delete_group(g.id, user_id=u.id, db=db)
                assert (await ra.list_groups(user_id=u.id, db=db)) == []
            finally:
                await db.close()
                await engine.dispose()
        asyncio.run(inner())


_C_SHARE_HTML = """
<div>侧栏 申购费率 链接</div>
<table><tr><td>管理费率</td><td>1.00%（每年）</td></tr>
<tr><td>托管费率</td><td>0.20%（每年）</td></tr></table>
<div>交易确认日 买入确认日 T+2 卖出确认日 T+2</div>
申购费率 <table><tr><td>适用金额</td><td>费率</td></tr>
<tr><td>---</td><td>0.00%</td></tr></table>
赎回费率 <table>
<tr><td>小于30天</td><td>1.50%</td></tr>
<tr><td>大于等于30天，小于730天</td><td>0.15%</td></tr>
<tr><td>大于等于730天</td><td>0.00%</td></tr></table>
"""


class TestParseCShare:
    def test_c_share_full_parse(self):
        p = parse_fee_html(_C_SHARE_HTML)
        assert p["mgmt_fee"] == 1.0
        assert p["custody_fee"] == 0.2
        assert p["purchase_fee"] == 0.0
        assert p["redeem_rules"] == [
            {"days": 30, "fee_rate": 1.5},
            {"days": 730, "fee_rate": 0.15},
            {"days": None, "fee_rate": 0.0},
        ]
        assert p["redeem_t_days"] == 2
