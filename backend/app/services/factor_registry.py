"""Preset factor registry (V2) — the single source of truth for factor definitions.

Categories (7): asset_class / style / industry / country / macro / statistical / alpha.

Each FactorDef maps onto the existing ``factors`` table columns:
- source        -> factors.data_source (akshare function name; '' for stubs)
- source_config -> factors.config (JSON, consumed by services/factor_sync.py)
- update_freq   -> factors.frequency
- data_status   -> factors.data_status ('ok' = syncable, 'stub' = no free source yet)

Transform semantics (how raw fetched series become factor_values kind='return'):
- pct            : 指数日涨跌幅（东财"涨跌幅"列 ÷100）
- index_pct      : 指数收盘价自行计算日收益
- proxy_diff     : 多头指数日收益 − 空头指数日收益
- level_diff     : 水平序列（收益率%/汇率值）日差分；除以100存小数
- monthly_ffill  : 月度值 ffill 到日频后，取月度值变化率（月对月 diff，日频平铺）÷100
- flow_zscore    : 日度流量/余额 → 20日滚动均值 → 日变化 → 全历史 zscore ÷10
- derived        : 服务端计算（statistical PCA），不走 akshare

Existing 7 legacy factors (equity/bond/credit_bond/gold/small_cap/overseas_equity/size)
stay as-is; ``ensure_factors()`` only upserts factors whose key is missing.
"""
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.factor import Factor

CATEGORIES = ["asset_class", "style", "industry", "country", "macro", "statistical", "alpha"]

CATEGORY_LABELS = {
    "asset_class": "资产类别",
    "style": "风格",
    "industry": "行业",
    "country": "国家/地区",
    "macro": "宏观",
    "statistical": "统计",
    "alpha": "Alpha信号",
}


@dataclass
class FactorDef:
    key: str
    name: str
    category: str
    definition: str = ""
    source: str = ""                                   # akshare function name; '' = stub
    source_config: dict = field(default_factory=dict)  # consumed by factor_sync
    transform: str = "pct"
    data_status: str = "ok"                            # ok | stub
    update_freq: str = "daily"
    is_market: bool = False


# ---------------------------------------------------------------- style ----
STYLE_FACTORS = [
    FactorDef(
        key="smb", name="规模SMB(中证1000−沪深300)", category="style",
        definition="小盘−大盘横截面多空收益代理：中证1000(000852)日收益 − 沪深300(000300)日收益",
        source="index_zh_a_hist", transform="proxy_diff",
        source_config={"long": "000852", "short": "000300"},
    ),
    FactorDef(
        key="value", name="价值HML(300价值−300成长)", category="style",
        definition="高BP−低BP代理：300价值(000919)日收益 − 300成长(000918)日收益",
        source="index_zh_a_hist", transform="proxy_diff",
        source_config={"long": "000919", "short": "000918"},
    ),
    FactorDef(
        key="dividend", name="股息(中证红利−沪深300)", category="style",
        definition="红利风格代理：中证红利(000922)日收益 − 沪深300(000300)日收益",
        source="index_zh_a_hist", transform="proxy_diff",
        source_config={"long": "000922", "short": "000300"},
    ),
    FactorDef(
        key="growth_style", name="成长(创业板指−沪深300)", category="style",
        definition="成长风格代理：创业板指(399006)日收益 − 沪深300(000300)日收益",
        source="index_zh_a_hist", transform="proxy_diff",
        source_config={"long": "399006", "short": "000300"},
    ),
    FactorDef(
        key="momentum", name="动量(代理:创业板−上证50)", category="style",
        definition="动量代理（高beta−低beta）：创业板指(399006)日收益 − 上证50(000016)日收益；注：官方动量指数无免费源，此为代理",
        source="index_zh_a_hist", transform="proxy_diff",
        source_config={"long": "399006", "short": "000016"},
    ),
    FactorDef(
        key="lowvol", name="低波动", category="style",
        definition="低波动−高波动多空组合。暂无已验证的免费低波指数日频数据源，预留接口",
        source="", transform="pct", data_status="stub",
    ),
]

# ------------------------------------------------------------- industry ----
# 申万2021一级行业（31个），index_hist_sw(symbol=code, period="day")
SW_L1: list[tuple[str, str, str]] = [
    ("801010", "agri", "农林牧渔"),
    ("801030", "chem_base", "基础化工"),
    ("801040", "steel", "钢铁"),
    ("801050", "nonferrous", "有色金属"),
    ("801080", "electronics", "电子"),
    ("801110", "home_appliance", "家用电器"),
    ("801120", "food_beverage", "食品饮料"),
    ("801130", "textile_apparel", "纺织服饰"),
    ("801140", "light_industry", "轻工制造"),
    ("801150", "pharma", "医药生物"),
    ("801160", "utilities", "公用事业"),
    ("801170", "transport", "交通运输"),
    ("801180", "real_estate", "房地产"),
    ("801200", "retail_trade", "商贸零售"),
    ("801210", "social_service", "社会服务"),
    ("801230", "conglomerate", "综合"),
    ("801710", "building_materials", "建筑材料"),
    ("801720", "building_deco", "建筑装饰"),
    ("801730", "power_equipment", "电力设备"),
    ("801740", "defense", "国防军工"),
    ("801750", "computer", "计算机"),
    ("801760", "media", "传媒"),
    ("801770", "telecom", "通信"),
    ("801780", "bank", "银行"),
    ("801790", "nonbank_fin", "非银金融"),
    ("801880", "auto", "汽车"),
    ("801890", "machinery", "机械设备"),
    ("801950", "coal", "煤炭"),
    ("801960", "petrochem", "石油石化"),
    ("801970", "env_protection", "环保"),
    ("801980", "beauty_care", "美容护理"),
]
INDUSTRY_FACTORS = [
    FactorDef(
        key=f"sw_{en}", name=f"申万{cn}", category="industry",
        definition=f"申万一级行业指数({code})日收益，行业共同收益因子",
        source="index_hist_sw", transform="index_pct",
        source_config={"symbol": code},
    )
    for code, en, cn in SW_L1
]

# -------------------------------------------------------------- country ----
COUNTRY_FACTORS = [
    FactorDef(
        key="us_equity", name="美股(标普500)", category="country",
        definition="标普500指数日收益（新浪美股指数）",
        source="index_us_stock_sina", transform="index_pct",
        source_config={"symbol": ".INX"},
    ),
    FactorDef(
        key="nasdaq", name="纳斯达克", category="country",
        definition="纳斯达克综合指数日收益（新浪美股指数）",
        source="index_us_stock_sina", transform="index_pct",
        source_config={"symbol": ".IXIC"},
    ),
    FactorDef(
        key="japan_equity", name="日本(日经225)", category="country",
        definition="日经225指数日收益（东财全球指数，中文名调用）",
        source="index_global_hist_em", transform="index_pct",
        source_config={"symbol": "日经225"},
    ),
    FactorDef(
        key="europe_equity", name="欧洲(德国DAX)", category="country",
        definition="德国DAX30指数日收益（东财全球指数，中文名调用）",
        source="index_global_hist_em", transform="index_pct",
        source_config={"symbol": "德国DAX30"},
    ),
    FactorDef(
        key="hk_equity", name="香港(恒生指数)", category="country",
        definition="恒生指数日收益（东财全球指数，中文名调用；若名称不在列表由sync降级为stub）",
        source="index_global_hist_em", transform="index_pct",
        source_config={"symbol": "恒生指数"},
    ),
]

# ---------------------------------------------------------------- macro ----
MACRO_FACTORS = [
    FactorDef(
        key="cn_rate", name="中国利率(10Y)", category="macro",
        definition="中国10年期国债收益率日变化（bp÷100存小数；利率上行为正）",
        source="bond_zh_us_rate", transform="level_diff",
        source_config={"column": "中国国债收益率10年"},
    ),
    FactorDef(
        key="us_rate", name="美国利率(10Y)", category="macro",
        definition="美国10年期国债收益率日变化（bp÷100存小数）",
        source="bond_zh_us_rate", transform="level_diff",
        source_config={"column": "美国国债收益率10年"},
    ),
    FactorDef(
        key="rate_curve", name="期限利差(10Y−2Y)", category="macro",
        definition="中国10Y−2Y国债利差日变化（bp÷100存小数）",
        source="bond_zh_us_rate", transform="level_spread_diff",
        source_config={"col_a": "中国国债收益率10年", "col_b": "中国国债收益率2年"},
    ),
    FactorDef(
        key="credit_spread", name="信用利差(AAA中票−国债)", category="macro",
        definition="中债AAA中短期票据收益率 − 中债国债收益率（同期限）日变化；bond_china_yield单窗<1年需按年循环",
        source="bond_china_yield", transform="credit_spread_diff",
        source_config={"curve_a": "中债中短期票据收益率曲线(AAA)", "curve_b": "中债国债收益率曲线", "tenor": "3月"},
    ),
    FactorDef(
        key="fx_usd", name="美元强弱(USDCNY)", category="macro",
        definition="美元/人民币中间价日收益率（人民币贬值=正）",
        source="macro_china_rmb", transform="level_pct",
        source_config={"item": "美元/人民币_中间价"},
    ),
    FactorDef(
        key="inflation", name="通胀(CPI同比)", category="macro",
        definition="CPI当月同比（月度值月度变化÷100，ffill日频）",
        source="macro_china_cpi_monthly", transform="monthly_ffill",
        source_config={"item": "CPI当月同比"},
    ),
    FactorDef(
        key="econ_growth", name="经济增长(PMI)", category="macro",
        definition="官方制造业PMI月度差分（ffill日频，÷100）",
        source="macro_china_pmi_yearly", transform="monthly_ffill_diff",
        source_config={"item": "官方制造业PMI"},
    ),
    FactorDef(
        key="commodity", name="商品(南华指数)", category="macro",
        definition="南华商品指数。akshare无该指数接口（调研确认），预留接口待接入",
        source="", transform="pct", data_status="stub",
    ),
    FactorDef(
        key="vol", name="波动率(VIX)", category="macro",
        definition="VIX恐慌指数。无免费日频历史源（调研确认），预留接口待接入",
        source="", transform="pct", data_status="stub",
    ),
]

# ---------------------------------------------------------- statistical ----
STATISTICAL_FACTORS = [
    FactorDef(
        key="stat_pca1", name="统计因子PC1", category="statistical",
        definition="入池基金日收益协方差矩阵第一主成分（每月末重算，日度沿用）",
        source="", transform="derived", update_freq="monthly",
    ),
    FactorDef(
        key="stat_pca2", name="统计因子PC2", category="statistical",
        definition="入池基金日收益协方差矩阵第二主成分",
        source="", transform="derived", update_freq="monthly",
    ),
    FactorDef(
        key="stat_pca3", name="统计因子PC3", category="statistical",
        definition="入池基金日收益协方差矩阵第三主成分",
        source="", transform="derived", update_freq="monthly",
    ),
]

# ----------------------------------------------------------------- alpha ----
ALPHA_FACTORS = [
    FactorDef(
        key="northbound", name="北向资金", category="alpha",
        definition="北向资金净流入20日均值日变化zscore（÷10缩放）；资金流入的正向alpha信号",
        source="stock_hsgt_fund_flow_summary_em", transform="flow_zscore",
        source_config={"net_col": "资金净流入", "ma": 20},
    ),
    FactorDef(
        key="margin", name="融资融券", category="alpha",
        definition="深市融资融券余额20日均值日变化zscore（÷10缩放）；杠杆资金信号；仅拉近2年（逐日接口限流）",
        source="stock_margin_szse", transform="flow_zscore",
        source_config={"balance_col": "融资融券余额", "ma": 20, "years": 2},
    ),
    FactorDef(
        key="moneyflow", name="主力资金流", category="alpha",
        definition="全市场个股主力净流入合计20日均值日变化zscore（÷10缩放）",
        source="stock_individual_fund_flow_rank", transform="flow_zscore",
        source_config={"indicator": "今日", "sum_col": "今日主力净流入-净额", "ma": 20},
    ),
    FactorDef(
        key="analyst", name="分析师预期", category="alpha",
        definition="分析师盈利预测修正。stock_profit_forecast_em仅有当前快照无历史时序，预留接口",
        source="", transform="pct", data_status="stub",
    ),
    FactorDef(
        key="sentiment", name="舆情", category="alpha",
        definition="市场舆情/新闻情绪。无免费数据源，预留接口",
        source="", transform="pct", data_status="stub",
    ),
    FactorDef(
        key="esg", name="ESG", category="alpha",
        definition="ESG评级。免费源仅股票级快照（stock_esg_*_sina），无法构成基金级日频序列，预留接口",
        source="", transform="pct", data_status="stub",
    ),
]

PRESET_FACTORS_V2 = STYLE_FACTORS + INDUSTRY_FACTORS + COUNTRY_FACTORS + MACRO_FACTORS + STATISTICAL_FACTORS + ALPHA_FACTORS


async def ensure_factors(db: AsyncSession) -> list[Factor]:
    """Upsert registry factors into the factors table (by key).

    - Missing key  -> insert new row (data_status from def).
    - Existing key -> update name/category/definition/data_source/config/frequency/data_status
      only (keep id, proxy_symbol, is_market and any Agent-built code).
    Legacy keys NOT in the registry are left untouched.
    """
    existing = {
        f.key: f
        for f in (await db.execute(select(Factor))).scalars().all()
        if f.key
    }
    created, updated = 0, 0
    for d in PRESET_FACTORS_V2:
        if d.key in existing:
            f = existing[d.key]
            f.name = d.name
            f.category = d.category
            f.definition = d.definition
            f.data_source = d.source
            f.config = _dump(d.source_config)
            f.frequency = d.update_freq
            f.data_status = d.data_status
            updated += 1
        else:
            f = Factor(
                name=d.name,
                key=d.key,
                category=d.category,
                definition=d.definition,
                data_source=d.source,
                config=_dump(d.source_config) if d.source_config else None,
                frequency=d.update_freq,
                proxy_symbol="",
                data_status=d.data_status,
            )
            db.add(f)
            created += 1
    await db.flush()
    print(f"[factor_registry] ensured {len(PRESET_FACTORS_V2)} factors (created={created}, updated={updated})", flush=True)
    return list((await db.execute(select(Factor))).scalars().all())


def _dump(cfg: dict) -> str:
    import json
    return json.dumps(cfg, ensure_ascii=False)
