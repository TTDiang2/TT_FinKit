"""命门诊断 7: THS_HQ 用 ths_unit_nv_fund 指标拉基金历史净值。"""
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

FUNDS = [("000217.OF", "华安黄金"), ("004243.OF", "广发道琼斯石油"), ("110001.OF", "易方达平稳")]

# ---- THS_HQ 用 ths_unit_nv_fund ----
print("=== THS_HQ ths_unit_nv_fund (近 30 天) ===")
for ths, name in FUNDS:
    for cps in ["", "CPS:1"]:
        try:
            d = iFinDPy.THS_HQ(ths, "ths_unit_nv_fund", cps, "2026-07-01", "2026-07-31")
            ec = getattr(d, "errorcode", "?")
            df = getattr(d, "data", None)
            cnt = len(df) if df is not None and hasattr(df, "__len__") else 0
            sample = None
            if cnt > 0:
                sample = df.head(2).to_dict("records")
            print(f"  {ths}({name}) CPS='{cps}': ec={ec}, {cnt} 条, sample={sample}")
        except Exception as e:
            print(f"  {ths} CPS='{cps}': 异常 {e}")

# ---- THS_HQ 试多个净值指标（unit_nv 可能不是 HQ 的正确名）----
print("\n=== THS_HQ 其他净值指标名 (000217.OF) ===")
for ind in ["ths_unit_nv_fund", "close", "ths_net_value", "ths_nav", "ths_unit_net_value", "settle"]:
    try:
        d = iFinDPy.THS_HQ("000217.OF", ind, "", "2026-07-01", "2026-07-31")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        cnt = len(df) if df is not None and hasattr(df, "__len__") else 0
        print(f"  {ind:30s}: ec={ec}, {cnt} 条")
    except Exception as e:
        print(f"  {ind}: 异常 {e}")

# ---- THS_DateSerial（THS_DS 的老接口）----
print("\n=== THS_DateSerial ths_unit_nv_fund (000217.OF) ===")
try:
    d = iFinDPy.THS_DateSerial("000217.OF", "ths_unit_nv_fund", "", "", "2026-07-01", "2026-07-31")
    ec = getattr(d, "errorcode", "?")
    df = getattr(d, "data", None)
    cnt = len(df) if df is not None and hasattr(df, "__len__") else 0
    print(f"  ec={ec}, {cnt} 条")
    if cnt > 0:
        print(df.head(2).to_string())
except Exception as e:
    print(f"  异常 {e}")

print("\n=== 诊断 7 完成 ===")
