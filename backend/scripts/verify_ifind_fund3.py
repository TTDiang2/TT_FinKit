"""命门诊断 3: 用正确的 THS_BD / THS_DS 签名试基金净值指标。

正确签名:
  THS_BD(thsCode, indicatorName, paramOption, format=...)
  THS_DS(thscode, jsonIndicator, jsonparam, globalparam, begintime, endtime, format=...)
"""
import sys, os, io, sqlite3
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.crypto import decrypt_field
from app.services import ifind_client
import iFinDPy

DB = r"finkit.db"
UID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"

conn = sqlite3.connect(DB)
row = conn.execute("SELECT ifind_username, ifind_password FROM user_settings WHERE user_id = ?", (UID,)).fetchone()
conn.close()
USER, PWD = row[0], decrypt_field(row[1])

ifind_client._login_sync(USER, PWD)
print("登录 OK\n")

FUNDS = [("000217.OF", "华安黄金"), ("004243.OF", "广发道琼斯石油")]
INDICATORS = [
    "ths_fund_net_value_fund",        # 单位净值
    "ths_fund_total_net_value_fund",  # 累计净值
]

# ---- THS_BD: 最新基本面 ----
print("=== THS_BD(ths, ind, '') ===")
for ths, name in FUNDS:
    for ind in INDICATORS:
        try:
            d = iFinDPy.THS_BD(ths, ind, "")
            ec = getattr(d, "errorcode", "?")
            df = getattr(d, "data", None)
            val = None
            if df is not None and hasattr(df, "iloc") and len(df) > 0:
                val = df.iloc[0, -1] if df.shape[1] >= 1 else None
            print(f"  {ths}({name}) {ind}: ec={ec}, val={val}")
        except Exception as e:
            print(f"  {ths} {ind}: 异常 {e}")

# ---- THS_DS: 历史净值序列 ----
print("\n=== THS_DS(ths, ind, '', '', begin, end) ===")
for ths, name in FUNDS:
    for ind in INDICATORS:
        try:
            d = iFinDPy.THS_DS(ths, ind, "", "", "2026-07-01", "2026-07-31")
            ec = getattr(d, "errorcode", "?")
            df = getattr(d, "data", None)
            cnt = 0
            sample = None
            if df is not None and hasattr(df, "iloc") and len(df) > 0:
                cnt = len(df)
                sample = df.head(2).to_dict("records")
            print(f"  {ths}({name}) {ind}: ec={ec}, {cnt} 条, sample={sample}")
        except Exception as e:
            print(f"  {ths} {ind}: 异常 {e}")

# ---- 备选: 试更多指标名（单位净值可能叫别的）----
print("\n=== THS_DS 备选指标名（000217.OF 2026-07）===")
alt_inds = [
    "ths_fund_unit_net_value_fund",
    "ths_unit_net_value_fund",
    "ths_net_value",
    "ths_nav",
    "ths_fund_net_value",
    "ths_open_fund_net_value",
    "ths_accumulated_net_value_fund",
]
for ind in alt_inds:
    try:
        d = iFinDPy.THS_DS("000217.OF", ind, "", "", "2026-07-01", "2026-07-31")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        cnt = len(df) if df is not None and hasattr(df, "__len__") else 0
        sample = None
        if cnt > 0:
            sample = df.head(2).to_dict("records")
        print(f"  {ind:42s}: ec={ec}, {cnt} 条, sample={sample}")
    except Exception as e:
        print(f"  {ind:42s}: 异常 {e}")

print("\n=== 诊断 3 完成 ===")
