"""Eastmoney (天天基金) fund profile fetcher + rule-based auto tagging.

三个来源：
1. ``ak.fund_purchase_em()`` 全表一次拉回（缓存 6h）→ 名称/类型/申购状态/
   赎回状态/购买起点/日累计限额。批量导入与批量更新的主数据源。
2. ``fundf10.eastmoney.com/jjfl_{code}.html`` → 管理费/托管费/销售服务费
   （HTML 正则，字段缺失容错返回 None）。
3. 持仓（十大重仓 + 资产配置）复用 ``asset_holdings`` 的 akshare 链路，
   仅用于打标，不在此模块重复实现。

``derive_tags`` 是纯函数：region / fund_kind / asset_class / theme tags。
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable, Optional

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_PURCHASE_TTL_S = 6 * 3600
_purchase_cache: dict = {"ts": 0.0, "table": {}}


def _ak():
    import akshare as ak
    return ak


_JJFL_URL = "https://fundf10.eastmoney.com/jjfl_{code}.html"


def normalize_daily_limit(v) -> Optional[float]:
    """日累计限定金额归一化：非数字文本 / >=1亿(站点“不限购”哨兵值 99999999999)
    都返回 None。"""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s or not re.fullmatch(r"[\d.]+", s):
            return None
        num = float(s)
    else:
        try:
            num = float(v)
        except (TypeError, ValueError):
            return None
    if num >= 1e8:
        return None
    return num


def get_purchase_table(provider: Optional[Callable[[], object]] = None) -> dict[str, dict]:
    """code -> {name, fund_type, purchase_status, redeem_status, min_buy, daily_limit}.

    全表缓存 6h；``provider`` 供测试注入假 akshare。
    """
    now = time.time()
    if _purchase_cache["table"] and now - _purchase_cache["ts"] < _PURCHASE_TTL_S:
        return _purchase_cache["table"]

    df = (provider or (lambda: _ak().fund_purchase_em()))()
    table: dict[str, dict] = {}
    if df is not None and not df.empty:
        def cell(row, col):
            v = row.get(col)
            return None if v is None or v != v else str(v).strip()

        for _, row in df.iterrows():
            code = cell(row, "基金代码")
            if not code:
                continue
            dlimit_f = normalize_daily_limit(cell(row, "日累计限定金额"))
            min_buy = cell(row, "购买起点")
            try:
                min_buy_f = float(min_buy.replace(",", "")) if min_buy else None
            except ValueError:
                min_buy_f = None
            table[code] = {
                "name": cell(row, "基金简称") or "",
                "fund_type": cell(row, "基金类型") or "",
                "purchase_status": cell(row, "申购状态") or "",
                "redeem_status": cell(row, "赎回状态") or "",
                "min_buy": min_buy_f,
                "daily_limit": dlimit_f,
            }
        _purchase_cache["ts"] = now
        _purchase_cache["table"] = table
    return table


_JJFL_PATTERNS = {
    "mgmt_fee": r"管理费率</td>\s*<td[^>]*>([\d.]+)\s*%",
    "custody_fee": r"托管费率</td>\s*<td[^>]*>([\d.]+)\s*%",
    "sales_service_fee": r"销售服务费率</td>\s*<td[^>]*>([\d.]+)\s*%",
}


def _seg(html: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    """截取 start_marker 之后的片段，直到最近的 end_marker（找不到则到文末）。"""
    i = html.find(start_marker)
    if i < 0:
        return ""
    rest = html[i + len(start_marker):]
    ends = [rest.find(m) for m in end_markers if rest.find(m) >= 0]
    return rest[: min(ends)] if ends else rest


def _fee_section(html: str, titles: tuple[str, ...], anchors: tuple[str, ...]) -> str:
    """定位费率小节：title 需在 300 字符内跟 anchors 之一；多处命中取最后一处
    （侧栏导航在页首，真实小节总在其后）。"""
    for title in titles:
        chosen = -1
        for m in re.finditer(re.escape(title), html):
            rest = html[m.end():m.end() + 300]
            if any(a in rest for a in anchors):
                chosen = m.start()
        if chosen >= 0:
            ends = tuple(e for e in ("class='sgfltip", '<div class="bo', "shwarn", "友情提示"))
            return _seg(html[chosen:], title, ends)
    return ""


def parse_fee_html(html: str) -> dict:
    """jjfl 页面 → 结构化费率。

    兼容两类版式：A 类「申购费率（前端）/（后端）」strike 优惠价；
    C 类无前后端标题、申购表为 ``适用金额 … 0.00%``。
    赎回行 ``大于等于X天，小于Y天`` 取上界 Y 档，尾部 ``大于等于N天`` 为兜底。
    附带解析「卖出确认日 T+N」→ redeem_t_days。
    """
    out: dict = {
        "mgmt_fee": None, "custody_fee": None, "sales_service_fee": None,
        "purchase_fee": None, "redeem_rules": [], "redeem_t_days": None,
    }
    for key, pat in _JJFL_PATTERNS.items():
        m = re.search(pat, html)
        if m:
            try:
                out[key] = float(m.group(1))
            except ValueError:
                pass

    buy_seg = _fee_section(
        html,
        ("申购费率（前端）", "申购费率"),
        ("<strike", "适用金额"),
    )
    m = re.search(
        r"<strike[^>]*>([\d.]+)\s*%</strike>(?:\s*(?:&nbsp;|<[^>]+>|\|)*?(?:([\d.]+)\s*%))?",
        buy_seg,
    )
    if not m:
        m = re.search(r"<td[^>]*>([\d.]+)\s*%", buy_seg)
        if m:
            out["purchase_fee"] = float(m.group(1))
    if m and m.lastindex and m.lastindex >= 2 and m.group(2):
        out["purchase_fee"] = float(m.group(2))       # 天天基金优惠价
    elif m and m.group(1):
        out["purchase_fee"] = float(m.group(1))       # 无优惠时原费率

    redeem_seg = _fee_section(
        html,
        ("赎回费率（前端）", "赎回费率"),
        ("适用期限", "小于"),
    )
    tiers: list[dict] = []
    for row_m in re.finditer(r"<tr><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td></tr>", redeem_seg, re.S):
        label_raw = re.sub(r"<[^>]+>|\s+", "", row_m.group(1))
        fee_m = re.search(r"([\d.]+)\s*%", re.sub(r"<[^>]+>", "", row_m.group(2)))
        if not fee_m:
            continue
        fee = float(fee_m.group(1))
        range_m = re.search(r"大于等于(\d+)天\s*[,，]\s*小于(\d+)天", label_raw)
        if range_m:
            tiers.append({"days": int(range_m.group(2)), "fee_rate": fee})
            continue
        uppers = [int(x) for x in re.findall(r"小于(\d+)天", label_raw)]
        if uppers:
            tiers.append({"days": min(uppers), "fee_rate": fee})
        elif "大于等于" in label_raw:
            tiers.append({"days": None, "fee_rate": fee})
    with_days = sorted((t for t in tiers if t["days"] is not None), key=lambda t: t["days"])
    fallback = [t for t in tiers if t["days"] is None]
    rules = with_days[:3]
    if fallback:
        rules.append(fallback[-1])
    seen_days: set[int | None] = set()
    valid_rules: list[dict] = []
    for t in rules:
        if t["days"] in seen_days:
            continue
        seen_days.add(t["days"])
        valid_rules.append(t)
    ok_order = all(
        valid_rules[i]["days"] is None or (valid_rules[i + 1]["days"] is None or valid_rules[i]["days"] < valid_rules[i + 1]["days"])
        for i in range(len(valid_rules) - 1)
    )
    out["redeem_rules"] = valid_rules if (valid_rules and ok_order) else []

    t_m = re.search(r"卖出确认日[^<]*?<[^>]*>\s*T\+(\d+)", html)
    if not t_m:
        t_m = re.search(r"卖出确认日[^\d]*T\+(\d+)", re.sub(r"<[^>]+>", "", html))
    if t_m:
        try:
            out["redeem_t_days"] = int(t_m.group(1))
        except ValueError:
            pass
    return out


def fetch_fee_profile(code: str) -> dict:
    """拉取并解析单只基金费率页；失败重试一次，仍失败返回全空结构。"""
    import requests

    def _once():
        r = requests.get(
            _JJFL_URL.format(code=code),
            headers={"User-Agent": _BROWSER_UA, "Referer": "https://fundf10.eastmoney.com/"},
            timeout=15,
        )
        r.raise_for_status()
        return parse_fee_html(r.text)

    empty = {k: None for k in ("mgmt_fee", "custody_fee", "sales_service_fee", "purchase_fee", "redeem_t_days")} | {"redeem_rules": []}
    for attempt in (0, 1):
        try:
            data = _once()
            if any(data.get(k) is not None for k in
                   ("mgmt_fee", "custody_fee", "purchase_fee")) or data["redeem_rules"]:
                return data
            empty = data          # 解析成功但全空：留作最后一次的结果
        except Exception:  # noqa: BLE001 — 费率为增强信息，失败不阻断导入
            if attempt == 1:
                return empty
    return empty


# --------------------------------------------------------------------------- #
# derive_tags — 纯函数打标
# --------------------------------------------------------------------------- #

_REGION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("纳斯达克", "标普", "道琼斯", "美国"), "QDII-美国"),
    (("恒生", "香港", "港股", "港币"), "QDII-香港"),
    (("新兴市场",), "QDII-新兴市场"),
    (("日本", "印度", "越南", "欧洲", "德国", "法国"), "QDII-其他"),
    (("全球", "国际"), "QDII-全球"),
)

# 名称含海外市场关键词但类型未标 QDII 时同样视为 QDII
_IMPLICIT_QDII_KEYWORDS = (
    "纳斯达克", "标普", "道琼斯", "恒生", "香港", "港股", "新兴市场",
    "日经", "印度", "越南", "德国", "法国", "海外", "美元", "美国",
)

_THEME_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("黄金",), "黄金"),
    (("原油", "石油", "油气", "石化能源"), "原油"),
    (("半导体", "芯片", "中芯", "华创", "韦尔", "长电", "兆易"), "半导体"),
    (("科技", "信息技术"), "科技"),
    (("消费", "白酒", "食品饮料", "酒"), "消费"),
    (("医药", "医疗", "生物"), "医药"),
    (("银行", "金融", "证券", "保险"), "大金融"),
    (("新能源", "光伏", "锂电", "碳中和", "宁德"), "新能源"),
    (("军工", "国防"), "军工"),
    (("互联网", "腾讯", "阿里"), "互联网"),
    (("地产", "房地产"), "地产"),
    (("基建", "工程"), "基建"),
)


def derive_tags(
    name: str,
    fund_type: str = "",
    top_holdings: Optional[list[dict]] = None,
    is_money_market: bool = False,
) -> dict:
    """从名称/类型/持仓推断 region / fund_kind / asset_class / auto_tags."""
    n = name or ""
    t = fund_type or ""

    is_qdii = (
        "QDII" in t.upper()
        or "qdii" in n.lower()
        or any(k in n for k in _IMPLICIT_QDII_KEYWORDS)
    )
    region = ""
    if is_qdii:
        region = "QDII-其他"
        for keys, val in _REGION_RULES:
            if any(k in n for k in keys):
                region = val
                break
    else:
        region = "境内"

    if is_money_market or "货币" in t:
        kind = "货币"
    elif "联接" in n:
        kind = "ETF联接"
    elif "ETF" in n.upper() and "%" not in n:
        kind = "ETF"
    elif "LOF" in n.upper():
        kind = "LOF"
    elif "FOF" in n.upper() or "养老" in t:
        kind = "FOF"
    elif "指数" in t or "指数" in n:
        kind = "指数增强" if "增强" in n else "指数跟踪"
    else:
        kind = "主动管理"

    blob = f"{n} {t}"
    holdings_blob = " ".join(str(h.get("name") or "") for h in (top_holdings or []))

    if kind == "货币":
        asset_class = "货币"
    elif "REIT" in blob.upper():
        asset_class = "另类"
    elif any(k in blob for k in ("黄金",)):
        asset_class = "商品-黄金"
    elif any(k in blob for k in ("原油", "石油", "商品", "豆粕", "期货")):
        asset_class = "另类"
    elif "债券" in t or ("债" in n and "转债" not in n and "股票" not in t):
        asset_class = "偏债"
    elif "股票" in t or "偏股" in t or is_qdii or kind in ("ETF", "ETF联接", "指数跟踪", "指数增强"):
        asset_class = "偏股"
    elif "混合" in t:
        asset_class = "混合"
    else:
        equity_ratio = sum(float(h.get("ratio") or 0) for h in (top_holdings or []))
        if equity_ratio >= 35:
            asset_class = "偏股"
        elif 5 < equity_ratio < 35:
            asset_class = "混合"
        else:
            asset_class = ""

    tags: list[str] = []
    for keys, label in _THEME_KEYWORDS:
        if any(k in n or k in holdings_blob for k in keys):
            tags.append(label)
    if any("HK" in str(h.get("name") or "").upper() or any(c.isascii() and c.isalpha() for c in str(h.get("name") or "")) for h in (top_holdings or [])):
        tags.append("含外盘持仓")

    return {"fund_kind": kind, "asset_class": asset_class, "region": region, "auto_tags": tags}


def note_from_tiers(tiers: list[dict]) -> str:
    def fmt(t):
        return f"<{t['days']}天 {t['fee_rate']:g}%" if t["days"] is not None else f"其余 {t['fee_rate']:g}%"
    return "；".join(fmt(t) for t in tiers)


def apply_profile(asset, profile: dict, fees: dict, holdings_payload: dict | None = None) -> list[str]:
    """把 profile/fees 写到 ResearchAsset 上，重算标签。返回被改动的字段名。

    fees 可为 get_purchase_table 行或 fetch_fee_profile 结果 —— 两者按存在的
    键合并消费；liquidity_note 是用户备注字段，绝不自动改写。
    """
    changed: list[str] = []

    def set_field(field, new_val):
        old = getattr(asset, field, None)
        if new_val is not None and new_val != old:
            setattr(asset, field, new_val)
            changed.append(field)

    if profile.get("name"):
        set_field("name", profile["name"])
    set_field("min_purchase", profile.get("min_buy"))
    set_field("purchase_limit", normalize_daily_limit(profile.get("daily_limit")))
    set_field("purchase_status", (profile.get("purchase_status") or "").strip() or None)
    for field in ("mgmt_fee", "custody_fee", "sales_service_fee", "purchase_fee"):
        v = fees.get(field) if fees else None
        if v is None and profile:
            v = profile.get(field)
        set_field(field, v)

    # T+N 只在缺失时补（用户手改优先，站点口径是“确认日”近似值）
    if getattr(asset, "redeem_t_days", None) is None and fees:
        set_field("redeem_t_days", fees.get("redeem_t_days"))

    tiers = (fees or {}).get("redeem_rules") or []
    if tiers:
        new_json = json.dumps(tiers, ensure_ascii=False)
        if asset.redeem_rules != new_json:
            asset.redeem_rules = new_json
            changed.append("redeem_rules")
        new_note = note_from_tiers(tiers)
        if (asset.redeem_fee_note or "") != new_note:
            asset.redeem_fee_note = new_note
            changed.append("redeem_fee_note")

    tags = derive_tags(
        asset.name, profile.get("fund_type") or "", (holdings_payload or {}).get("top_holdings"),
        bool(asset.is_money_market),
    )
    before_tags = getattr(asset, "auto_tags") or "[]"
    new_tags_json = json.dumps(tags["auto_tags"], ensure_ascii=False)
    for field in ("fund_kind", "asset_class", "region"):
        set_field(field, tags[field])
    if new_tags_json != before_tags:
        setattr(asset, "auto_tags", new_tags_json)
        changed.append("auto_tags")

    from datetime import datetime
    asset.profile_synced_at = datetime.utcnow()
    return changed


PROFILE_MAX_AGE_DAYS = 30


def audit_violations(asset) -> tuple[list[str], list[str]]:
    """入池审查。返回 (硬违规→必须剔除, 软缺失→先试更新再定)。

    硬：申购状态非开放 / 限额<1000元。
    软：管/托费率缺失、档案过期（>30 天）。
    """
    hard: list[str] = []
    soft: list[str] = []

    status = (getattr(asset, "purchase_status", "") or "").strip()
    if status and status != "开放申购":
        hard.append(f"申购状态「{status}」")
    limit = getattr(asset, "purchase_limit", None)
    if limit is not None and limit < 1000:
        hard.append(f"日限额 {limit:g} 元 < 1000")

    if getattr(asset, "mgmt_fee", None) is None:
        soft.append("管理费缺失")
    if getattr(asset, "custody_fee", None) is None:
        soft.append("托管费缺失")
    synced_at = getattr(asset, "profile_synced_at", None)
    from datetime import datetime
    fresh = False
    if synced_at is not None:
        try:
            fresh = (datetime.utcnow() - synced_at).days <= PROFILE_MAX_AGE_DAYS
        except TypeError:
            fresh = False
    if not fresh:
        soft.append("档案未同步或过期")
    return hard, soft


def read_auto_tags(raw: Optional[str]) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        return [str(x) for x in data] if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []
