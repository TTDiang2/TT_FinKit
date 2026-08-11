"""命门诊断 5: 找正确的基金净值指标名。

已知: ths_fund_type_fund 能用(返回"契约型开放式"), ths_fund_net_value_fund 不行(-209)。
策略: 用 iwencai 自然语言查净值(返回带正确指标标识) + 穷举 BD 指标名。
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
row = conn.execute("SELECT ifind_username, ifind_password FROM user_settings WHERE user_id=?", (UID,)).fetchone()
conn.close()
ifind_client._login_sync(row[0], decrypt_field(row[1]))
print("登录 OK\n")

# ---- 1. iwencai 自然语言查（返回含正确指标标识）----
print("=== THS_iwencai 自然语言查净值 ===")
for q in ["000217.OF 最新净值", "华安黄金000217 单位净值 累计净值", "000217 基金净值"]:
    try:
        r = iFinDPy.THS_iwencai(q)
        print(f"\n--- query: {q} ---")
        print(f"  type={type(r).__name__}")
        if hasattr(r, "errorcode"):
            print(f"  errorcode={r.errorcode}")
        if hasattr(r, "data") and r.data is not None:
            df = r.data
            if hasattr(df, "columns"):
                print(f"  columns: {list(df.columns)}")
                print(f"  shape: {df.shape}")
                print(df.head(3).to_string())
            else:
                print(f"  data: {str(df)[:600]}")
    except Exception as e:
        print(f"  query='{q}': 异常 {e}")

# ---- 2. 穷举 BD 净值指标名 ----
print("\n=== 穷举 BD 基金净值指标名 (000217.OF) ===")
candidates = [
    "ths_fund_unit_nv_fund",           # 单位净值
    "ths_fund_acc_nv_fund",            # 累计净值
    "ths_fund_nv_fund",                # 净值
    "ths_fund_net_asset_value_fund",   # 净资产值
    "ths_fund_latest_nv_fund",         # 最新净值
    "ths_fund_end_nv_fund",            # 期末净值
    "ths_fund_unit_netvalue_fund",     # 单位净值(无下划线)
    "ths_unit_nv_fund",
    "ths_fund_jz_fund",                # 净值拼音
    "ths_nev_fund",
    "ths_fund_netvalue_fund",          # 合并
    "ths_fund_pub_date_fund",          # 净值发布日(对照)
    "ths_fund_scale_fund",             # 规模(对照)
]
for ind in candidates:
    try:
        d = iFinDPy.THS_BD("000217.OF", ind, "")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        val = None
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            val = df.iloc[0, -1] if df.shape[1] >= 1 else None
        marker = "✓" if ec == 0 else " "
        print(f"  {marker} {ind:42s}: ec={ec}, val={val}")
    except Exception as e:
        print(f"    {ind:42s}: 异常 {e}")

print("\n=== 诊断 5 完成 ===")
