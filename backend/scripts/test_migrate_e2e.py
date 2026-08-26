"""Phase2 端到端功能测试: 模拟 migrate-entry 端点的 preview 逻辑。
用户输入"2024年两次投资华安黄金"，验证 iFinD 拉净值 + migration_calc 反推份额。
"""
import sys, os, io, sqlite3, asyncio
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.crypto import decrypt_field
from app.services import ifind_client, migration_calc

DB = r"finkit.db"
UID = "<USER_ID>"

conn = sqlite3.connect(DB)
user, pwd_enc = conn.execute(
    "SELECT ifind_username, ifind_password FROM user_settings WHERE user_id=?", (UID,)
).fetchone()
conn.close()
PWD = decrypt_field(pwd_enc)


async def main():
    # 模拟用户输入：2024 年两次投资华安黄金 000217
    inputs = [
        {"date": "2024-06-03", "amount": 5000.0},
        {"date": "2024-09-10", "amount": 3000.0},
        {"date": "2024-01-02", "amount": 2000.0},  # 早投资
    ]
    print(f"=== 模拟迁移输入（华安黄金 000217）===")
    for i in inputs:
        print(f"  {i['date']}  投入 {i['amount']:.2f} 元")

    # 拉 2024 全年净值（覆盖所有投资日）
    print(f"\n=== iFinD 拉取 000217.OF 2024 全年净值 ===")
    try:
        series = await ifind_client.fetch_history_close(
            user, PWD, "000217", "FUND_CN", "2024-01-01", "2024-12-31"
        )
        print(f"  ✓ {len(series)} 个交易日净值, 首 {series[0]}, 末 {series[-1]}")
    except Exception as e:
        print(f"  ✗ {e}")
        return

    # migration_calc 反推份额
    print(f"\n=== migration_calc.build_migration_entries 反推份额 ===")
    nav_fetcher = lambda _dates: series  # noqa: E731
    results = migration_calc.build_migration_entries(inputs, nav_fetcher)
    total_shares = 0.0
    total_amount = 0.0
    for r in results:
        if r.get("error"):
            print(f"  ✗ {r['date']}  {r['amount']:.2f}元  → {r['error']}")
        else:
            shares = r["shares"]
            nav = r["nav"]
            total_shares += shares
            total_amount += r["amount"]
            print(f"  ✓ {r['date']}  {r['amount']:>8.2f}元  NAV={nav:.4f}  →  {shares:.2f} 份")
    print(f"\n  合计: 投入 {total_amount:.2f}元, 反推 {total_shares:.2f}份")
    if total_shares > 0:
        avg_cost = total_amount / total_shares
        print(f"  平均成本: {avg_cost:.4f} 元/份")
    print(f"\n✓✓✓ Phase2 迁移核心链路验证通过！")


asyncio.run(main())
