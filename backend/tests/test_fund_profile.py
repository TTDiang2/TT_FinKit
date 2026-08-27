"""fund_profile: 打标规则 / 限额归一化 / 费率页解析 / purchase 表解析 / 审查规则。"""
from types import SimpleNamespace

import pandas as pd

from app.services.fund_profile import (
    apply_profile,
    audit_violations,
    derive_tags,
    get_purchase_table,
    normalize_daily_limit,
    parse_fee_html,
    read_auto_tags,
)


def test_region_domestic_and_qdii():
    assert derive_tags("南方天天利货币B")["region"] == "境内"
    assert derive_tags("国泰纳斯达克100ETF", "股票指数")["region"] == "QDII-美国"
    assert derive_tags("华夏恒生互联网科技业ETF联接", "QDII")["region"] == "QDII-香港"
    assert derive_tags("工银瑞信全球精选", "QDII-混合")["region"] == "QDII-全球"
    assert derive_tags("嘉实新兴市场A", "QDII-股票")["region"] == "QDII-新兴市场"


def test_fund_kind_rules():
    assert derive_tags("沪深300ETF", "股票指数")["fund_kind"] == "ETF"
    assert derive_tags("黄金ETF联接C", "混合-偏债")["fund_kind"] == "ETF联接"
    assert derive_tags("景顺长城新兴成长混合", "混合型-偏股")["fund_kind"] == "主动管理"
    assert derive_tags("易方达优质精选混合(QDII)", "QDII-混合")["fund_kind"] == "主动管理"
    assert derive_tags("招商中证白酒指数A", "股票指数")["fund_kind"] == "指数跟踪"
    assert derive_tags("富国中证红利指数增强A", "股票指数-增强")["fund_kind"] == "指数增强"
    assert derive_tags("天弘余额宝货币", "货币型")["fund_kind"] == "货币"


def test_asset_class_rules():
    assert derive_tags("中证全指债券ETF", "债券指数")["asset_class"] == "偏债"
    assert derive_tags("华安黄金ETF", "商品指数")["asset_class"] == "商品-黄金"
    assert derive_tags("嘉实原油", "另类")["asset_class"] == "另类"
    assert derive_tags("兴全趋势投资混合", "混合型-灵活")["asset_class"] == "混合"
    assert derive_tags("华夏上证50ETF", "股票指数")["asset_class"] == "偏股"
    assert derive_tags("广发纳斯达克100ETF联接", "QDII-指数")["asset_class"] == "偏股"


def test_theme_tags_from_name_and_holdings():
    t = derive_tags(
        "诺安成长混合", "混合型-偏股",
        top_holdings=[{"name": "中芯国际", "ratio": 9.5}, {"name": "北方华创", "ratio": 8.1}],
    )
    assert "半导体" in t["auto_tags"]
    t2 = derive_tags("华宝标普油气上游股票", "QDII-股票")
    assert "原油" in t2["auto_tags"]
    # 境内名称带港股但非 QDII → region 仍为境内
    assert derive_tags("前海开源沪港深优势精选混合", "混合型-偏股")["region"] == "境内"


def test_purchase_table_parsing():
    def fake_ak():
        class _FakeAK:
            def fund_purchase_em(self_inner):
                return pd.DataFrame([
                    {"基金代码": "000217", "基金简称": "上投摩根平衡型混合", "基金类型": "混合型-平衡",
                     "申购状态": "开放申购", "赎回状态": "开放赎回",
                     "购买起点": "10.00", "日累计限定金额": "1000000.00"},
                    {"基金代码": "006432", "基金简称": "金鹰添瑞中短债C", "基金类型": "债券型-中短债",
                     "申购状态": "暂停申购", "赎回状态": "开放赎回",
                     "购买起点": "10.00", "日累计限定金额": "暂不限购"},
                ])
        return _FakeAK()

    table = get_purchase_table(provider=fake_ak().fund_purchase_em)
    assert table["000217"]["daily_limit"] == 1000000.0
    assert table["000217"]["min_buy"] == 10.0
    assert table["006432"]["daily_limit"] is None  # 非数字文本 → 未限额
    assert table["006432"]["purchase_status"] == "暂停申购"


def test_normalize_daily_limit():
    assert normalize_daily_limit(99999999999.0) is None   # 站点“不限购”哨兵值
    assert normalize_daily_limit("暂不限购") is None
    assert normalize_daily_limit(None) is None
    assert normalize_daily_limit("") is None
    assert normalize_daily_limit("1,000") == 1000.0
    assert normalize_daily_limit(1000) == 1000.0


_FEE_HTML = """
<div><table class="w770 comm jjfl"><tbody><tr><td class="th w110">管理费率</td><td class="w135">1.20%（每年）</td>
<td class="th w110">托管费率</td><td class="w135">0.20%（每年）</td>
<td class="th w110">销售服务费率</td><td class="w135">0.00%（每年）</td></tr></tbody></table></div>
<h4>申购费率（前端）</h4><table class="w650 comm jjfl"><tbody>
<tr><td class="">小于100万元</td><td><strike class='gray'>1.50%</strike>&nbsp;&nbsp;|&nbsp;&nbsp;0.15%</td></tr>
<tr><td class="">大于等于100万元，小于1000万元</td><td><strike class='gray'>1.20%</strike>&nbsp;&nbsp;|&nbsp;&nbsp;0.12%</td></tr>
</tbody></table>
<h4>赎回费率（前端）<a name="shfl"></a></h4><table class="w650 comm jjfl"><tbody>
<tr><td>小于7天</td><td>1.50%</td></tr>
<tr><td>大于等于7天，小于30天</td><td>0.50%</td></tr>
<tr><td>大于等于30天</td><td>0.10%</td></tr>
</tbody></table>
"""


def test_parse_fee_html_full():
    fees = parse_fee_html(_FEE_HTML)
    assert fees["mgmt_fee"] == 1.2
    assert fees["custody_fee"] == 0.2
    assert fees["sales_service_fee"] == 0.0
    assert fees["purchase_fee"] == 0.15          # 首档天天基金优惠价
    tiers = fees["redeem_rules"]
    assert tiers[0] == {"days": 7, "fee_rate": 1.5}
    assert {"days": 30, "fee_rate": 0.5} in tiers  # 区间中间档取上界
    assert tiers[-1] == {"days": None, "fee_rate": 0.1}


def _asset(**kw):
    from datetime import datetime
    base = dict(
        symbol="000217", name="X", mgmt_fee=1.5, custody_fee=0.25,
        purchase_status="开放申购", purchase_limit=None,
        profile_synced_at=datetime.utcnow(),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_audit_violations_rules():
    from datetime import datetime, timedelta
    hard, soft = audit_violations(_asset())
    assert not hard and not soft

    hard, _ = audit_violations(_asset(purchase_status="暂停申购"))
    assert hard == ["申购状态「暂停申购」"]

    hard, _ = audit_violations(_asset(purchase_limit=500))
    assert hard == ["日限额 500 元 < 1000"]
    hard, _ = audit_violations(_asset(purchase_limit=500000))
    assert not hard                                  # 50万 OK

    old = datetime.utcnow() - timedelta(days=40)
    _, soft = audit_violations(_asset(profile_synced_at=old))
    assert any("过期" in s for s in soft)
    _, soft = audit_violations(_asset(mgmt_fee=None))
    assert any("管理费" in s for s in soft)


def test_apply_profile_no_liquidity_overwrite():
    a = SimpleNamespace(
        symbol="000217", name="旧名", min_purchase=None, purchase_limit=None,
        purchase_status="", mgmt_fee=None, custody_fee=None,
        sales_service_fee=None, purchase_fee=None,
        redeem_rules="[]", redeem_fee_note="", liquidity_note="用户手写备注",
        fund_kind="", asset_class="", region="", auto_tags="[]",
        is_money_market=False, profile_synced_at=None,
    )
    changed = apply_profile(
        a,
        {"name": "华安黄金ETF联接C", "fund_type": "指数型-其他", "min_buy": 10.0,
         "daily_limit": 99999999999.0, "purchase_status": "开放申购"},
        {"mgmt_fee": 0.5, "custody_fee": 0.1, "sales_service_fee": None,
         "purchase_fee": 0.15, "redeem_rules": [{"days": 7, "fee_rate": 1.5}, {"days": None, "fee_rate": 0}]},
    )
    assert "liquidity_note" not in changed
    assert a.liquidity_note == "用户手写备注"
    assert a.purchase_limit is None                   # 哨兵值→None
    assert a.purchase_status == "开放申购"
    assert a.mgmt_fee == 0.5 and a.purchase_fee == 0.15
    assert a.name == "华安黄金ETF联接C"
    assert '"days": null' in a.redeem_rules or "'days': None" in str(a.redeem_rules)


def test_read_auto_tags_tolerant():
    assert read_auto_tags(None) == []
    assert read_auto_tags("") == []
    assert read_auto_tags('not json') == []
    assert read_auto_tags('["黄金","半导体"]') == ["黄金", "半导体"]
