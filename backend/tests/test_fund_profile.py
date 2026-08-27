"""fund_profile: derive_tags 打标规则 + purchase 表解析(注入假 provider)。"""
import pandas as pd

from app.services.fund_profile import derive_tags, get_purchase_table, read_auto_tags


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


def test_read_auto_tags_tolerant():
    assert read_auto_tags(None) == []
    assert read_auto_tags("") == []
    assert read_auto_tags('not json') == []
    assert read_auto_tags('["黄金","半导体"]') == ["黄金", "半导体"]
