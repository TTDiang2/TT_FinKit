#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
建行流水转换脚本：hqmx_*.xls  →  finkit_import.xlsx

把中国建设银行的交易明细 xls 转成 FinKit 通用的导入 xlsx。
脚本会做初步打标（分类、转账识别），打标置信度低的行会留空并标黄，
用户在 Excel 里复核后再上传到 FinKit 导入。

用法：
    python ccb_to_import.py <建行流水.xls> [输出.xlsx]
    python ccb_to_import.py                              # 用默认样例

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

# 建行这张卡的持卡人姓名（用于识别"给自己转账"）。对方户名与此一致 → 视为本人在他行的账户。
# 留空 = 不启用本人识别，所有转账 dest_account 都留空待填。
SELF_HOLDER_NAMES = []  # 例如 ['持卡人姓名']

# 本方账户：建行这张卡在 FinKit 里对应的账户名
DEFAULT_ACCOUNT = "消费账户"

# FinKit 账户清单（用于 dest_account 下拉）。改成你自己的账户名。
ACCOUNT_OPTIONS = ["消费账户", "工资账户", "投资账户"]

# 摘要 → 直接判定为转账（transfer），dest_account 留空待用户填
TRANSFER_SUMMARIES = {"汇兑", "普通汇兑", "充值"}

# 摘要包含这些词 → 收入（退款/利息类）
INCOME_SUMMARY_CONTAINS = ["退货", "退费", "利息存入", "利息"]

# 分类打标规则（按优先级，先匹配者胜）。命中后停止。
# (关键词列表, 分类名) —— 在【对方户名 + 摘要】拼接文本里匹配。
# 分类名必须存在于你的 FinKit 支出/收入分类中。
EXPENSE_RULES = [
    # 医疗
    (["医院", "医药", "药房", "诊所", "大药房", "牙科"], "医疗"),
    # 餐饮/美食
    (["大学", "学校", "食堂", "面包", "餐", "食", "味", "面馆", "饺子", "饺",
      "粉", "饭", "茶", "咖啡", "奶茶", "饮品", "烤", "肉", "鸡", "汉堡",
      "德基", "麦", "甜品", "糕", "寿喜", "涮", "火锅", "串", "烧", " baker",
      "果茶", "便利食品"], "美食"),
    # 网购/购物
    (["便利", "超市", "百货", "商店", "购物", "旗舰", "物联", "电商", "市场",
      "生鲜", "京东", "淘宝", "天猫", "拼多多", "得物", "苏宁"], "网购"),
    # 衣物
    (["衣", "服饰", "鞋", "耐克", "阿迪", "优衣库", "zara", "hm "], "衣物"),
    # 酒店
    (["酒店", "宾馆", "住宿", "民宿", "旅馆", "亚朵", "希尔顿", "如家"], "酒店"),
    # 旅游/交通（用户用"高铁"泛指交通）
    (["携程", "旅行", "旅游", "航空", "机票", "飞猪", "去哪儿", "八达通",
      "octopus", "滴滴", "出租", "地铁", "公交", "铁路", "12306", "单车",
      "出行", "打车"], "高铁"),
    # 娱乐
    (["电影", "游戏", "娱乐", "演出", "steam", "ktv", "密室", "剧本"], "娱乐"),
    # 生活杂项（缴费类：水电煤话费物业）
    (["电费", "水费", "燃气", "物业", "宽带", "话费", "联通", "移动", "电信",
      "充）", "充电", "加油", "加油站", "中石化", "中石油"], "生活杂项"),
    # 旅游
    (["旅行", "旅游", "景点", "门票", "古寺", "乐园"], "旅游"),
]

INCOME_RULES = [
    # 默认收入都归零碎收入（工资这张卡没有，如出现"工资/代发"才归工资）
    (["工资", "代发", "薪水", "薪资"], "工资"),
    (["奖", "奖金"], "奖金"),
    (["利息", "退税"], "利息、退款等零碎收入"),
]

INCOME_FALLBACK = "利息、退款等零碎收入"  # 收入默认分类（退款等）

# =====================================================================
# 解析建行 xls
# =====================================================================

def parse_ccb_xls(path):
    """返回 list[dict]：每笔交易的标准化中间结构。"""
    book = xlrd.open_workbook(path)
    sh = book.sheet_by_index(0)

    # 找表头行（含"摘要"字样的行）
    header_row = None
    for i in range(min(10, sh.nrows)):
        row_vals = [str(sh.cell_value(i, c)).strip() for c in range(sh.ncols)]
        if any("摘要" in v for v in row_vals):
            header_row = i
            break
    if header_row is None:
        raise RuntimeError("未找到表头行（含'摘要'），请检查文件格式")

    headers = [str(sh.cell_value(header_row, c)).strip() for c in range(sh.ncols)]
    # 列名定位（兼容建行不同版本）
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
    col_channel = find_col("交易地点") or find_col("渠道")
    col_counterparty = find_col("对方账号")

    if None in (col_summary, col_date, col_amount):
        raise RuntimeError(f"缺少关键列。表头：{headers}")

    rows = []
    for i in range(header_row + 1, sh.nrows):
        seq = sh.cell_value(i, col_seq) if col_seq is not None else ""
        # 跳过尾部汇总行（序号空或非数字）
        if col_seq is not None:
            try:
                int(float(seq))
            except (ValueError, TypeError):
                continue

        summary = str(sh.cell_value(i, col_summary)).strip()
        date_raw = str(sh.cell_value(i, col_date)).strip()
        amount_raw = sh.cell_value(i, col_amount)
        balance_raw = sh.cell_value(i, col_balance) if col_balance is not None else ""
        counterparty = str(sh.cell_value(i, col_counterparty)).strip() if col_counterparty is not None else ""
        channel = str(sh.cell_value(i, col_channel)).strip() if col_channel is not None else ""

        # 日期 YYYYMMDD → YYYY-MM-DD
        date_norm = normalize_date(date_raw)
        # 金额（可能是字符串带千分位/括号，或 float）
        amount, is_negative = normalize_amount(amount_raw)
        balance = parse_amount_float(balance_raw)

        if amount == 0:
            continue

        rows.append({
            "seq": seq,
            "summary": summary,
            "date": date_norm,
            "amount": amount,            # 正数
            "sign": -1 if is_negative else 1,
            "balance": balance,
            "counterparty": counterparty,
            "channel": channel,
        })
    return rows


def normalize_date(s):
    s = s.replace("-", "").replace("/", "").replace(" ", "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    # 尝试 xlrd date
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
    """返回 (正数金额, 是否为负)"""
    x = parse_amount_float(v)
    return (abs(x), x < 0)


# =====================================================================
# 打标
# =====================================================================

def classify(row):
    """返回 (direction, category, dest_account, note)
    direction: income / expense / transfer
    category: 分类名（可能为 ""）
    dest_account: 转账对方账户（仅 transfer，可能为 ""）
    note: 打标说明
    """
    summary = row["summary"]
    cp = row["counterparty"]
    text = f"{summary} {cp}"
    is_income_amount = row["sign"] > 0   # 正金额

    # 1. 转账优先（用户选"激进"）
    if summary in TRANSFER_SUMMARIES:
        dest = match_self_account(cp)
        return ("transfer", "", dest,
                "转账-待确认对方" if not dest else "转账-本人账户")

    # 2. 退款/利息 → 收入
    if any(k in summary for k in INCOME_SUMMARY_CONTAINS) or is_income_amount:
        cat = match_rule(text, INCOME_RULES) or INCOME_FALLBACK
        return ("income", cat, "", "收入")

    # 3. 支出 —— 按规则打标
    cat = match_rule(text, EXPENSE_RULES)
    if cat:
        return ("expense", cat, "", f"命中:{cat}")
    return ("expense", "", "", "未命中规则-待手动")


def match_self_account(counterparty):
    """对方户名里若出现 SELF_HOLDER_NAMES，猜测是本人账户。
    建行单账户流水无法确定，默认返回空。"""
    if not SELF_HOLDER_NAMES:
        return ""
    for name in SELF_HOLDER_NAMES:
        if name in counterparty:
            return "工资账户"  # 猜测，用户可改
    return ""


def match_rule(text, rules):
    """rules: [(关键词列表, 分类), ...]。文本含任一关键词即命中。"""
    text_lower = text.lower()
    for keywords, category in rules:
        for kw in keywords:
            if kw.lower() in text_lower:
                return category
    return ""


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
    ("tags",          "标签",          8),
    ("description",   "描述",         16),
    ("remark",        "备注",         12),
    ("source_memo",   "原始摘要",     14),
    ("counterparty",  "对方户名",     30),
    ("status",        "打标状态",     18),
]

# 填充颜色
YELLOW = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")  # 待确认
GREEN = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")   # 已打标
HEADER_FILL = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
THIN = Side(border_style="thin", color="D4D4D4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def write_import_xlsx(rows, out_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "import"

    # 表头
    for ci, (_, label, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=ci, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[1].height = 24
    ws.freeze_panes = "A2"

    # 数据
    stats = Counter()
    for ri, row in enumerate(rows, start=2):
        direction, category, dest_account, note = classify(row)
        stats[direction] += 1
        if not category and direction != "transfer":
            stats["unlabeled"] += 1
        if direction == "transfer" and not dest_account:
            stats["transfer_pending"] += 1

        values = {
            "date":         row["date"],
            "direction":    direction,
            "amount":       row["amount"],
            "account":      DEFAULT_ACCOUNT,
            "dest_account": dest_account,
            "category":     category,
            "tags":         "",
            "description":  row["summary"],
            "remark":       "",
            "source_memo":  row["summary"],
            "counterparty": row["counterparty"],
            "status":       note,
        }
        for ci, (key, _, _) in enumerate(COLUMNS, start=1):
            c = ws.cell(row=ri, column=ci, value=values[key])
            c.border = BORDER
            c.alignment = Alignment(vertical="center",
                                    horizontal="left" if ci >= 9 else "center")
            if COLUMNS[ci - 1][0] == "amount":
                c.number_format = "#,##0.00"

    # 下拉验证
    n_rows = len(rows) + 1
    dv_dir = DataValidation(type="list", formula1='"income,expense,transfer"', allow_blank=False)
    dv_acc = DataValidation(type="list", formula1='"' + ",".join(ACCOUNT_OPTIONS) + '"', allow_blank=True)
    dv_cat = DataValidation(type="list",
                            formula1='"旅游,酒店,网购,美食,住房,衣物,生活杂项,高铁,娱乐,医疗,投资亏损,退款冲销,工资,奖金,投资,家庭支持,学校补贴,奖学金,利息、退款等零碎收入"',
                            allow_blank=True)
    ws.add_data_validation(dv_dir)
    ws.add_data_validation(dv_acc)
    ws.add_data_validation(dv_cat)
    dv_dir.add(f"B2:B{n_rows}")
    dv_acc.add(f"D2:D{n_rows}")
    dv_acc.add(f"E2:E{n_rows}")
    dv_cat.add(f"F2:F{n_rows}")

    # 条件格式：待确认行整行标黄
    # 条件1：方向=transfer 且 对方账户为空
    # 条件2：分类为空（非转账）
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    ws.conditional_formatting.add(
        f"A2:L{n_rows}",
        FormulaRule(formula=[f'AND($B2="transfer",$E2="")'], fill=yellow_fill, stopIfTrue=False)
    )
    ws.conditional_formatting.add(
        f"A2:L{n_rows}",
        FormulaRule(formula=[f'AND($B2<>"transfer",$F2="")', f'$F2=""'], fill=yellow_fill, stopIfTrue=False)
    )
    # 上面第二个公式写得有问题，重写：方向非转账 且 分类为空
    # openpyxl 不支持修改已添加规则，这里用更精确的公式重新覆盖
    ws.conditional_formatting._cf_rules.clear()
    ws.conditional_formatting.add(
        f"A2:L{n_rows}",
        FormulaRule(formula=['AND($B2="transfer",$E2="")'], fill=yellow_fill)
    )
    ws.conditional_formatting.add(
        f"A2:L{n_rows}",
        FormulaRule(formula=['AND($B2<>"transfer",LEN($F2)=0)'], fill=yellow_fill)
    )

    wb.save(out_path)
    return stats


# =====================================================================
# main
# =====================================================================

def main():
    if len(sys.argv) >= 2:
        in_path = sys.argv[1]
    else:
        in_path = r"hqmx_export.xls"
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
    stats = write_import_xlsx(rows, out_path)

    print()
    print("=== 打标统计 ===")
    print(f"  支出 expense      : {stats['expense']}")
    print(f"  收入 income       : {stats['income']}")
    print(f"  转账 transfer     : {stats['transfer']}（其中 {stats['transfer_pending']} 条待填对方账户）")
    print(f"  分类未命中(待手动): {stats['unlabeled']}")
    print()
    print("提示：标黄的行需要你在 Excel 里手动补全分类/对方账户，然后上传到 FinKit 导入。")


if __name__ == "__main__":
    main()
