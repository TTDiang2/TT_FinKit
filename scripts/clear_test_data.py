#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清除测试数据：删除 FinKit 中指定时间段、指定账户的交易数据。
用于"交易内容自动识别"任务的反复导入测试。

用法：
    python scripts/clear_test_data.py                          # 默认：2026-04-01 ~ 2026-07-31，消费账户
    python scripts/clear_test_data.py 2026-04-01 2026-07-31    # 指定时间段
    python scripts/clear_test_data.py 2026-04-01 2026-07-31 消费账户  # 指定账户名

需要先停止后端服务（避免 SQLite 锁），或在后端未运行时执行。
"""
import sys
import os
import sqlite3
from datetime import datetime

# 默认参数
DEFAULT_START = "2026-04-01"
DEFAULT_END = "2026-07-31"
DEFAULT_ACCOUNT = "消费账户"

# 数据库路径（backend/finkit.db，相对于本脚本位置）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "finkit.db")


def clear(start_date: str, end_date: str, account_name: str) -> None:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: 数据库不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 找到账户 ID
    cur.execute("SELECT id FROM accounts WHERE name = ?", (account_name,))
    row = cur.fetchone()
    if not row:
        print(f"ERROR: 账户不存在: {account_name}")
        # 列出所有账户供参考
        cur.execute("SELECT name FROM accounts")
        names = [r[0] for r in cur.fetchall()]
        print(f"  现有账户: {names}")
        conn.close()
        sys.exit(1)
    account_id = row[0]

    # 统计待删除（account_id 是本方或对方；type 为 income/expense/transfer 都算）
    # 注意：转账可能 account_id 或 dest_account_id 命中
    cur.execute(
        """SELECT COUNT(*), type FROM transactions
           WHERE (account_id = ? OR dest_account_id = ?)
             AND date >= ? AND date <= ?
           GROUP BY type""",
        (account_id, account_id, start_date, end_date),
    )
    stats = cur.fetchall()
    total = sum(s[0] for s in stats)
    if total == 0:
        print(f"没有匹配的数据（{account_name} {start_date}~{end_date}），无需清除。")
        conn.close()
        return

    print(f"待删除：{account_name} {start_date}~{end_date}，共 {total} 条")
    for cnt, t in stats:
        print(f"  {t}: {cnt}")

    # 确认
    confirm = input("确认删除？输入 yes 继续：").strip().lower()
    if confirm != "yes":
        print("已取消。")
        conn.close()
        return

    # 删除
    cur.execute(
        """DELETE FROM transactions
           WHERE (account_id = ? OR dest_account_id = ?)
             AND date >= ? AND date <= ?""",
        (account_id, account_id, start_date, end_date),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    print(f"已删除 {deleted} 条。")


def main():
    start_date = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_START
    end_date = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_END
    account_name = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_ACCOUNT

    # 简单校验日期格式
    for d in (start_date, end_date):
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: 日期格式错误: {d}（需 YYYY-MM-DD）")
            sys.exit(1)

    print(f"数据库: {DB_PATH}")
    clear(start_date, end_date, account_name)


if __name__ == "__main__":
    main()
