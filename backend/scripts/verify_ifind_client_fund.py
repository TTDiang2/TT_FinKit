"""端到端验证 ifind_client.py 对 .OF 基金的 fetch_realtime/fetch_history_close。
确认 FUND_CN 分流走 THS_BD/THS_DS + ths_unit_nv_fund 正确工作。
"""
import sys, os, io, sqlite3, asyncio
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.crypto import decrypt_field
from app.services import ifind_client

DB = r"finkit.db"
UID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"
conn = sqlite3.connect(DB)
row = conn.execute("SELECT ifind_username, ifind_password FROM user_settings WHERE user_id=?", (UID,)).fetchone()
conn.close()
USER, PWD = row[0], decrypt_field(row[1])
print(f"凭证: {USER}\n")

FUNDS = [
    ("000217", "华安黄金"),
    ("004243", "广发道琼斯石油"),
    ("110001", "易方达平稳"),
    ("017895", "汇添富纳指生物"),
]


async def main():
    # 1) fetch_realtime (THS_BD ths_unit_nv_fund)
    print("=== fetch_realtime (FUND_CN → THS_BD) ===")
    for sym, name in FUNDS:
        try:
            r = await ifind_client.fetch_realtime(USER, PWD, sym, "FUND_CN")
            print(f"  ✓ {sym} {name}: NAV={r['price']}, thscode={r['thscode']}")
        except Exception as e:
            print(f"  ✗ {sym} {name}: {e}")

    # 2) fetch_history_close (THS_DS ths_unit_nv_fund)
    print("\n=== fetch_history_close (FUND_CN → THS_DS, 2026-07) ===")
    for sym, name in FUNDS:
        try:
            series = await ifind_client.fetch_history_close(
                USER, PWD, sym, "FUND_CN", "2026-07-01", "2026-07-31"
            )
            first, last = series[0], series[-1]
            print(f"  ✓ {sym} {name}: {len(series)} 条, "
                  f"首 {first['date']}={first['close']}, 末 {last['date']}={last['close']}")
        except Exception as e:
            print(f"  ✗ {sym} {name}: {e}")

    # 3) 确认股票路径不受影响（回归）
    print("\n=== 回归: 股票 fetch_realtime (SH → THS_RQ) ===")
    try:
        r = await ifind_client.fetch_realtime(USER, PWD, "600519", "SH")
        print(f"  ✓ 600519 茅台: price={r['price']}, name={r['name']}")
    except Exception as e:
        print(f"  ✗ 600519: {e}")

    print("\n=== 验证完成 ===")


asyncio.run(main())
