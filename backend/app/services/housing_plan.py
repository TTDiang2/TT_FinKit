"""购房目标画像 — 参数可编辑，快照与前端同源。

参数存在 user_settings.monitor_thresholds JSON 的 `advisor_housing` 键下，
与「个人画像」(advisor_profile) 并列，避免新增表。

## 为什么把公积金写进来
用户的公积金月缴额（个人+公司合计 12,960）是购房测算里量级最大的变量：
- 年累积 155,520，5 年不计息即 777,600 —— 相当于南京首付的 90%
- 公积金可直接冲抵月供，因此"月供安全上限"不能只按到手现金算
不写进快照，AI 只能按到手现金推算，会显著低估购房能力。
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user_settings import UserSettings

# 默认假设（用户 2026-09-04 确认）：90㎡ 刚需，南京 3.2 万/平、上海 6.5 万/平，5 年内
DEFAULT_HOUSING = {
    "target_cities": ["nanjing", "shanghai"],
    "area_sqm": 90,
    "unit_price_per_sqm": {"nanjing": 32000, "shanghai": 65000},
    "target_years": 5,
    "down_payment_ratio": 0.30,
    "family_support_cap": 2_000_000,
    "mortgage_rate_annual": 0.031,     # 首套商贷 30 年参考利率
    "mortgage_years": 30,
    "housing_fund_monthly_total": 12960,   # 个人 6480 + 公司 6480
    "housing_fund_own_monthly": 6480,
    "net_monthly_income": 27000,       # 税后到手
    "gross_monthly_income": 40000,     # 税前
    "monthly_payment_safety_ratio": 0.35,  # 月供 / 到手月收入 上限
}

CITY_LABELS = {"nanjing": "南京", "shanghai": "上海"}


def _monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """等额本息月供。"""
    if principal <= 0:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12
    if r == 0:
        return principal / n
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


async def get_housing_plan(db: AsyncSession, user_id: str) -> dict:
    row = (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
           ).scalar_one_or_none()
    saved: dict = {}
    if row and row.monitor_thresholds:
        try:
            saved = json.loads(row.monitor_thresholds).get("advisor_housing") or {}
        except (ValueError, TypeError):
            saved = {}
    return {**DEFAULT_HOUSING, **saved}


async def save_housing_plan(db: AsyncSession, user_id: str, patch: dict) -> dict:
    row = (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
           ).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
    current: dict = {}
    if row.monitor_thresholds:
        try:
            current = json.loads(row.monitor_thresholds)
        except (ValueError, TypeError):
            current = {}
    merged = {**(current.get("advisor_housing") or DEFAULT_HOUSING), **(patch or {})}
    current["advisor_housing"] = merged
    row.monitor_thresholds = json.dumps(current, ensure_ascii=False)
    await db.commit()
    return merged


def build_housing_snapshot(plan: dict) -> dict:
    """把购房参数展开成 AI 可直接引用的场景测算。"""
    area = float(plan.get("area_sqm") or 0)
    ratio = float(plan.get("down_payment_ratio") or 0.3)
    rate = float(plan.get("mortgage_rate_annual") or 0.031)
    years = int(plan.get("mortgage_years") or 30)
    prices = plan.get("unit_price_per_sqm") or {}
    cities = plan.get("target_cities") or list(prices.keys())

    hf_monthly = float(plan.get("housing_fund_monthly_total") or 0)
    hf_annual = hf_monthly * 12
    target_years = float(plan.get("target_years") or 5)
    net_income = float(plan.get("net_monthly_income") or 0)
    safety = float(plan.get("monthly_payment_safety_ratio") or 0.35)
    cash_payment_cap = net_income * safety          # 现金可承受月供上限
    total_payment_cap = cash_payment_cap + hf_monthly  # 公积金可全额冲抵月供

    scenarios = []
    for key in cities:
        price = float(prices.get(key) or 0)
        if not price or not area:
            continue
        total = price * area
        down = total * ratio
        loan = total - down
        mp = _monthly_payment(loan, rate, years)
        scenarios.append({
            "city": CITY_LABELS.get(key, key),
            "city_key": key,
            "unit_price_per_sqm": round(price),
            "area_sqm": area,
            "est_total_price": round(total),
            "down_payment": round(down),
            "down_payment_ratio": ratio,
            "mortgage_principal": round(loan),
            "mortgage_years": years,
            "mortgage_rate_annual": rate,
            "monthly_payment": round(mp),
            # 公积金冲抵后的现金月供压力
            "monthly_payment_after_fund": round(max(0.0, mp - hf_monthly)),
            "monthly_payment_vs_net_income": round(mp / net_income, 4) if net_income else None,
            "affordable_by_cash_cap": round(mp) <= cash_payment_cap,
            "affordable_with_fund": round(mp) <= total_payment_cap,
        })

    return {
        "target_cities": [CITY_LABELS.get(c, c) for c in cities],
        "area_sqm": area,
        "target_years": target_years,
        "down_payment_ratio": ratio,
        "family_support_cap": plan.get("family_support_cap"),
        "housing_fund": {
            "monthly_total": hf_monthly,
            "own_monthly": plan.get("housing_fund_own_monthly"),
            "company_monthly": round(hf_monthly - float(plan.get("housing_fund_own_monthly") or 0)),
            "annual_accumulation": round(hf_annual),
            "accumulation_by_target_year": round(hf_annual * target_years),
            "note": "公积金属强制储蓄：不可用于日常开销，但可直接冲抵月供/"
                    "提取付首付。测算月供承受力时必须计入，否则会低估购房能力。",
        },
        "income_for_mortgage": {
            "net_monthly_income": net_income,
            "gross_monthly_income": plan.get("gross_monthly_income"),
            "safety_ratio": safety,
            "cash_payment_cap": round(cash_payment_cap),
            "total_payment_cap_incl_fund": round(total_payment_cap),
        },
        "scenarios": scenarios,
        "note": "以上为按设定参数的机械测算，未含税费/装修/契税/利率浮动；"
                "首付缺口需与快照中的应急储备约束交叉校验（不得掏空应急金）。",
    }
