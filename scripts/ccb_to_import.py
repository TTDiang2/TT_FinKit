#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
建行流水转换脚本：hqmx_*.xls  →  finkit_import.xlsx

把中国建设银行的交易明细 xls 转成 FinKit 通用的导入 xlsx。
基于"交易地点/附言"字段做分类识别，输出每行的识别置信度。

用法：
    python ccb_to_import.py <建行流水.xls> [输出.xlsx]
    python ccb_to_import.py                              # 用当前目录下默认文件名 hqmx_export.xls

设计文档/字段定义见 FinKit docs。
"""
import sys
import os
from datetime import datetime
from collections import Counter

import xlrd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter

# =====================================================================
# CONFIG — 按需修改
# =====================================================================

# 建行这张卡的持卡人姓名（用于识别"工资转入"）。对方户名含此名 + 电子汇入 → 工资转入。
# 留空 = 不启用本人识别，所有转账 dest_account 都留空待填。
SELF_HOLDER_NAMES = []  # 例如 ['持卡人姓名']

# 本方账户：建行这张卡在 FinKit 里对应的账户名
DEFAULT_ACCOUNT = "消费账户"

# 工资转入时对方账户（转账来源）
SALARY_ACCOUNT = "工资账户"

# FinKit 账户清单（用于 dest_account 下拉）
ACCOUNT_OPTIONS = ["消费账户", "工资账户", "投资账户"]

# 转账摘要（汇兑类）
TRANSFER_SUMMARIES = {"汇兑", "普通汇兑"}

# 摘要 → 直接判定为消费退货（负支出）
REFUND_SUMMARIES = {"消费退货"}

# 摘要 → 收入（利息/退税/退费）
INCOME_SUMMARIES = {"利息存入"}
# 交易地点含这些词 → 收入（退税/退费）
INCOME_LOCATION_CONTAINS = ["电子退库", "退费"]

# 有效的支出分类（投资亏损/退款冲销已移除，契合簿记逻辑）
EXPENSE_CATEGORIES = ["旅游", "酒店", "网购", "美食", "住房", "衣物", "生活杂项", "高铁", "娱乐", "医疗", "打车"]
INCOME_CATEGORIES = ["工资", "奖金", "投资", "家庭支持", "学校补贴", "奖学金", "利息、退款等零碎收入"]

# 分类打标规则（按优先级，先匹配者胜）。
# 每条规则: (关键词列表, 分类, 置信度)
# 匹配范围：交易地点/附言 + 对方户名 + 摘要 拼接文本（小写）
# 置信度: "high"（精确品牌/强信号）/ "medium"（关键词模糊）
EXPENSE_RULES = [
    # === 高置信度：精确品牌 ===
    # 打车
    (["高德打车", "滴滴出行", "滴滴打车", "花小猪"], "打车", "high"),
    # 高铁/铁路/地铁/公交/交通卡
    (["中国铁路网络", "中国铁路集团", "12306", "上海新上铁", "新上铁", "铁路",
      "南京地铁", "地铁运营", "申通地铁", "公共交通卡", "交通卡", "上海申通",
      "首都机场", "首都国际机场", "star ferry", "天星码头", "明珠公用卡", "公用卡"], "高铁", "high"),
    # 盒马 → 生活杂项
    (["盒马"], "生活杂项", "high"),
    # 学校/教育缴费 → 生活杂项（用户确认）
    (["上海交通大学", "交通大学"], "生活杂项", "high"),
    # 云裳物联/魔盒 → 生活杂项（用户确认）
    (["云裳物联", "魔盒", "citybox"], "生活杂项", "high"),
    # 亚朵 → 酒店（>2000 走旅游，在 classify 里特殊处理）
    (["亚朵"], "酒店", "high"),
    # 娱乐：订阅、电影、游戏
    (["apple music", "app store", "netflix", "spotify", "steam", "猫眼", "电影", "游戏", "演出", "ktv", "密室", "剧本",
      "深度求索", "deepseek", "游侠", "游泳馆"], "娱乐", "high"),
    # 网购：电商
    (["淘宝", "天猫", "京东", "拼多多", "得物", "苏宁", "抖音商城", "7-11", "seven", "罗森", " Lawson",
      "九木杂物社", "杂物社"], "网购", "high"),
    # 医疗
    (["大药房", "老百姓大药房", "药店", "医院", "医药", "诊所", "牙科"], "医疗", "high"),
    # 生活杂项：水电煤话费宽带
    (["中国电信", "中国联通", "中国移动", "电费", "水费", "燃气", "物业", "宽带", "话费"], "生活杂项", "high"),
    # 酒店
    (["桔子酒店", "如家", "汉庭", "全季", "希尔顿", "民宿", "旅馆", "宾馆"], "酒店", "high"),
    # 旅游：景点/旅行社
    (["携程", "飞猪", "去哪儿", "八达通", "octopus", "迪士尼", "环球影城", "乐园", "景点", "门票",
      "森林公园", "钟山风景区", "钟山风景区", "长生鹿苑", "夫子庙", "同程文旅", "清华印象",
      "小火车", "飞碟", "海战船", "导览图", "古寺", "龙华古寺"], "旅游", "high"),
    # 住房
    (["房租", "租金", "金帆", "紫金和寓", "和寓"], "住房", "high"),
    # 衣物
    (["优衣库", "zara", "耐克", "阿迪达斯", "海澜之家"], "衣物", "high"),
    # 美食：精确品牌（餐厅/饮品/快餐）
    (["萨莉亚", "蜜雪冰城", "dq", "koi", "肯德基", "kfc", "麦当劳", "胖哥俩", "喜家德",
      "蘇小柳", "苏小柳", "来伊份", "黄鱼面", "拉面", "糖水铺", "臭豆腐", "岚山breakfast",
      "coffee", "paper stone", "boneless", "八号黄油", "黄豆仙人", "壹福", "一尺花园",
      "蘩楼", "ramen", "泉膳", "闽台千里香", "地摊牛排", "砂锅", "海鲜", "水饺",
      "果港", "申美甲谐", "什饮智能", "乐摩吧",
      "香江姳苑", "姳苑", "花甲", "gelato", "todos", "龙华会"], "美食", "high"),

    # === 中置信度：关键词模糊 ===
    # 打车（补充）
    (["出租", "网约车", "出行"], "打车", "medium"),
    # 美食（食物词；美团/大众点评团购默认归美食）
    (["美团", "大众点评", "餐", "食", "味", "面馆", "饺子", "粉", "饭", "茶", "咖啡", "奶茶", "饮品",
      "烤", "肉", "鸡", "汉堡", "甜品", "糕", "寿喜", "涮", "火锅", "串", "烧",
      "便利食品", "料理", "点心", "粤菜", "小吃", "食堂", "面包", " baker"], "美食", "medium"),
    # 网购（补充）
    (["便利", "超市", "百货", "商店", "购物", "旗舰", "电商", "生鲜"], "网购", "medium"),
    # 衣物（补充）
    (["衣", "服饰", "鞋", "服装"], "衣物", "medium"),
    # 酒店（补充）
    (["酒店", "住宿"], "酒店", "medium"),
    # 医疗（补充）
    (["药房", "医药"], "医疗", "medium"),
    # 生活杂项（充值/缴费/智能柜/便民）
    (["丰巢", "充电", "加油", "中石化", "中石油", "骑行", "单车", "哈啰", "智能柜", "鲲鲸",
      "慈善", "基金会", "骑安"], "生活杂项", "medium"),
]

INCOME_RULES = [
    (["工资", "代发", "薪水", "薪资"], "工资", "high"),
    (["奖", "奖金"], "奖金", "high"),
    (["利息", "退税", "退费"], "利息、退款等零碎收入", "high"),
]
INCOME_FALLBACK = "利息、退款等零碎收入"

# 亚朵/酒店 金额阈值：超过此值视为旅游（长住/度假）
HOTEL_TO_TOURISM_THRESHOLD = 2000.0


# =====================================================================
# 解析建行 xls
# =====================================================================

def parse_ccb_xls(path):
    """返回 list[dict]：每笔交易的标准化中间结构。"""
    book = xlrd.open_workbook(path)
    sh = book.sheet_by_index(0)

    header_row = None
    for i in range(min(10, sh.nrows)):
        row_vals = [str(sh.cell_value(i, c)).strip() for c in range(sh.ncols)]
        if any("摘要" in v for v in row_vals):
            header_row = i
            break
    if header_row is None:
        raise RuntimeError("未找到表头行（含'摘要'），请检查文件格式")

    headers = [str(sh.cell_value(header_row, c)).strip() for c in range(sh.ncols)]

    def find_col(*keywords):
        for idx, h in enumerate(headers):
            for kw in keywords:
                if kw in h:
                    return idx
        return None

    col_seq = find_col("序号")
    col_summary = find_col("摘要")
    col_date = find_col("交易日期")
    col_amount = find_col("交易金额")
    col_balance = find_col("账户余额") or find_col("余额")
    col_location = find_col("交易地点") or find_col("渠道") or find_col("附言")
    col_counterparty = find_col("对方账号")

    if None in (col_summary, col_date, col_amount):
        raise RuntimeError(f"缺少关键列。表头：{headers}")

    rows = []
    for i in range(header_row + 1, sh.nrows):
        seq = sh.cell_value(i, col_seq) if col_seq is not None else ""
        if col_seq is not None:
            try:
                int(float(seq))
            except (ValueError, TypeError):
                continue

        summary = str(sh.cell_value(i, col_summary)).strip()
        date_raw = str(sh.cell_value(i, col_date)).strip()
        amount_raw = sh.cell_value(i, col_amount)
        balance_raw = sh.cell_value(i, col_balance) if col_balance is not None else ""
        counterparty_full = str(sh.cell_value(i, col_counterparty)).strip() if col_counterparty is not None else ""
        location = str(sh.cell_value(i, col_location)).strip() if col_location is not None else ""

        counterparty_name = extract_counterparty_name(counterparty_full)

        date_norm = normalize_date(date_raw)
        amount, is_negative = normalize_amount(amount_raw)
        balance = parse_amount_float(balance_raw)

        if amount == 0:
            continue

        rows.append({
            "seq": seq,
            "summary": summary,
            "date": date_norm,
            "amount": amount,
            "sign": -1 if is_negative else 1,
            "balance": balance,
            "counterparty_full": counterparty_full,
            "counterparty_name": counterparty_name,
            "location": location,
        })
    return rows


def extract_counterparty_name(counterparty_full: str) -> str:
    """从 '4******9202/*建钦' 提取户名（/ 后部分）。"""
    if "/" in counterparty_full:
        return counterparty_full.split("/", 1)[1].strip()
    return counterparty_full.strip()


def normalize_date(s):
    s = s.replace("-", "").replace("/", "").replace(" ", "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    try:
        return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return s


def parse_amount_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if not v:
        return 0.0
    s = str(v).strip().replace(",", "").replace("，", "")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    try:
        x = float(s)
    except ValueError:
        return 0.0
    return -x if neg else x


def normalize_amount(v):
    x = parse_amount_float(v)
    return (abs(x), x < 0)


# =====================================================================
# 打标（分类识别）
# =====================================================================

def classify(row):
    """返回 (direction, category, dest_account, confidence, note, negate)
    direction: income / expense / transfer
    category: 分类名（可能为 ""）
    dest_account: 转账对方账户（仅 transfer）
    confidence: "high" / "medium" / "low" / "none"
    note: 打标说明
    negate: True = 金额取负（消费退货，记负支出冲销）
    """
    summary = row["summary"]
    cp_name = row["counterparty_name"]
    location = row["location"]
    amount = row["amount"]
    is_income_amount = row["sign"] > 0
    text = f"{location} {cp_name} {summary}".lower()

    # 1. 消费退货 → 负支出，按交易地点推断原分类
    if summary in REFUND_SUMMARIES:
        cat, conf = match_expense(text)
        return ("expense", cat, "", conf, f"退款冲销:{cat}" if cat else "退款-未识别分类", True)

    # 2. 利息存入 → 收入
    if summary in INCOME_SUMMARIES:
        return ("income", INCOME_FALLBACK, "", "high", "利息收入", False)

    # 3. 转账：汇兑 + 电子汇入 + 本人户名 → 工资转入
    if summary in TRANSFER_SUMMARIES:
        is_self = any(name in cp_name for name in SELF_HOLDER_NAMES)
        if "电子汇入" in location and is_self:
            return ("transfer", "", SALARY_ACCOUNT, "high", "工资转入", False)
        # 普通汇兑 + 电子退库 → 退税（收入）
        if any(k in location for k in INCOME_LOCATION_CONTAINS):
            return ("income", INCOME_FALLBACK, "", "high", "退税/退费收入", False)
        # 其他汇兑 + 本人 → 转账
        if is_self:
            return ("transfer", "", SALARY_ACCOUNT, "medium", "转账-本人账户", False)
        return ("transfer", "", SALARY_ACCOUNT, "low", "汇兑-待确认", False)

    # 4. 退费类摘要 → 收入
    if any(k in summary for k in INCOME_LOCATION_CONTAINS) or "退费" in summary:
        return ("income", INCOME_FALLBACK, "", "high", "退费收入", False)

    # 5. 充值 → 看交易地点：微信扫码/红包/群收款是消费
    if summary == "充值":
        if any(k in location for k in ["扫二维码", "红包", "群收款", "微信支付"]):
            cat, conf = match_expense(text)
            return ("expense", cat or "生活杂项", "", conf or "medium",
                    f"充值消费:{cat}" if cat else "充值消费-默认生活杂项", False)
        return ("expense", "生活杂项", "", "low", "充值-默认生活杂项", False)

    # 6. 消费/缴费/有卡自助消费 → 支出，按规则识别
    cat, conf = match_expense(text)
    if cat:
        # 亚朵特殊：>2000 → 旅游
        if cat == "酒店" and "亚朵" in text and amount > HOTEL_TO_TOURISM_THRESHOLD:
            return ("expense", "旅游", "", conf, f"亚朵大额→旅游(>{HOTEL_TO_TOURISM_THRESHOLD})", False)
        return ("expense", cat, "", conf, f"命中:{cat}", False)
    return ("expense", "", "", "none", "未命中规则-待手动", False)


def match_expense(text: str):
    """返回 (分类, 置信度)。按 EXPENSE_RULES 优先级匹配。"""
    text_lower = text.lower()
    for keywords, category, confidence in EXPENSE_RULES:
        for kw in keywords:
            if kw.lower() in text_lower:
                return (category, confidence)
    return ("", "none")


# =====================================================================
# 写出 xlsx
# =====================================================================

COLUMNS = [
    ("date",          "交易日期",    12),
    ("direction",     "方向",         10),
    ("amount",        "金额",         10),
    ("account",       "本方账户",     12),
    ("dest_account",  "对方账户",     12),
    ("category",      "分类",         14),
    ("confidence",    "置信度",       10),
    ("tags",          "标签",          8),
    ("description",   "描述",         20),
    ("location",      "交易地点/附言", 30),
    ("remark",        "备注",         12),
    ("counterparty",  "对方户名",     18),
    ("status",        "打标状态",     22),
]

HEADER_FILL = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
THIN = Side(border_style="thin", color="D4D4D4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def clean_description(location: str) -> str:
    """从交易地点/附言清洗出简短描述（去掉支付渠道前缀）。"""
    s = location
    for prefix in ("支付宝-支付宝外部商户-", "支付宝-支付宝-消费-", "支付宝-支付宝-",
                   "财付通-微信支付-", "美团支付-美团app-", "美团支付-",
                   "京东支付-京东商城-", "京东支付-", "支付宝-淘宝-", "支付宝-天猫-"):
        if s.lower().startswith(prefix.lower()):
            s = s[len(prefix):]
            break
    return s.strip()


def write_import_xlsx(rows, out_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "import"

    for ci, (_, label, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=ci, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[1].height = 24
    ws.freeze_panes = "A2"

    stats = Counter()
    by_confidence = Counter()
    for ri, row in enumerate(rows, start=2):
        direction, category, dest_account, confidence, note, negate = classify(row)
        stats[direction] += 1
        by_confidence[confidence] += 1
        if not category and direction != "transfer":
            stats["unlabeled"] += 1

        description = clean_description(row["location"]) or row["summary"]
        values = {
            "date":         row["date"],
            "direction":    direction,
            "amount":       -row["amount"] if negate else row["amount"],
            "account":      DEFAULT_ACCOUNT,
            "dest_account": dest_account,
            "category":     category,
            "confidence":   confidence,
            "tags":         "",
            "description":  description,
            "location":     row["location"],
            "remark":       "",
            "counterparty": row["counterparty_full"],
            "status":       note,
        }
        for ci, (key, _, _) in enumerate(COLUMNS, start=1):
            c = ws.cell(row=ri, column=ci, value=values[key])
            c.border = BORDER
            c.alignment = Alignment(vertical="center", horizontal="left" if ci >= 7 else "center")
            if COLUMNS[ci - 1][0] == "amount":
                c.number_format = "#,##0.00"

    n_rows = len(rows) + 1
    dv_dir = DataValidation(type="list", formula1='"income,expense,transfer"', allow_blank=False)
    dv_acc = DataValidation(type="list", formula1='"' + ",".join(ACCOUNT_OPTIONS) + '"', allow_blank=True)
    dv_cat = DataValidation(type="list",
                            formula1='"' + ",".join(EXPENSE_CATEGORIES + INCOME_CATEGORIES) + '"',
                            allow_blank=True)
    dv_conf = DataValidation(type="list", formula1='"high,medium,low,none"', allow_blank=True)
    ws.add_data_validation(dv_dir)
    ws.add_data_validation(dv_acc)
    ws.add_data_validation(dv_cat)
    ws.add_data_validation(dv_conf)
    dv_dir.add(f"B2:B{n_rows}")
    dv_acc.add(f"D2:D{n_rows}")
    dv_acc.add(f"E2:E{n_rows}")
    dv_cat.add(f"F2:F{n_rows}")
    dv_conf.add(f"G2:G{n_rows}")

    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    orange_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    ws.conditional_formatting.add(f"A2:M{n_rows}", FormulaRule(formula=['$G2="none"'], fill=orange_fill))
    ws.conditional_formatting.add(f"A2:M{n_rows}", FormulaRule(formula=['OR($G2="medium",$G2="low")'], fill=yellow_fill))

    wb.save(out_path)
    return stats, by_confidence


def main():
    if len(sys.argv) >= 2:
        in_path = sys.argv[1]
    else:
        in_path = "hqmx_export.xls"  # 默认文件名；样例数据不随仓库分发，请传入你的建行流水文件
    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
    else:
        base = os.path.splitext(os.path.basename(in_path))[0]
        out_path = os.path.join(os.path.dirname(in_path) or ".", f"finkit_import_{base}.xlsx")

    if not os.path.exists(in_path):
        print(f"ERROR: 输入文件不存在: {in_path}")
        sys.exit(1)

    print(f"解析建行流水: {in_path}")
    rows = parse_ccb_xls(in_path)
    print(f"解析到 {len(rows)} 笔交易")

    print(f"写出导入模板: {out_path}")
    stats, by_conf = write_import_xlsx(rows, out_path)

    print()
    print("=== 方向统计 ===")
    print(f"  支出 expense      : {stats['expense']}")
    print(f"  收入 income       : {stats['income']}")
    print(f"  转账 transfer     : {stats['transfer']}")
    print(f"  分类未命中(待手动): {stats['unlabeled']}")
    print()
    print("=== 置信度统计 ===")
    total = sum(by_conf.values())
    for conf in ("high", "medium", "low", "none"):
        cnt = by_conf.get(conf, 0)
        pct = cnt / total * 100 if total else 0
        print(f"  {conf:6s}: {cnt:4d} ({pct:.1f}%)")
    print()
    identified = by_conf.get("high", 0) + by_conf.get("medium", 0)
    rate = identified / total * 100 if total else 0
    print(f"识别率(high+medium): {identified}/{total} = {rate:.1f}%")
    print()
    print("提示：橙色=未识别分类(待手动)；黄色=中/低置信度(建议检查)；其余=已识别。")


if __name__ == "__main__":
    main()
