"""命门调试: 穷举 iFinD 对场外开放式基金 (000217 华安黄金) 的 thscode 后缀 + 字段组合。

之前 THS_RQ("000217.OF","latest","") 和 THS_HQ("000217.OF","close",...) 都 -4001 no data。
本脚本穷举字段名 + 后缀，找出能返回净值的组合。
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.utils.crypto import decrypt_field
import iFinDPy

USER_ID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"
DB = os.path.join(os.path.dirname(__file__), "..", "backend", "finkit.db")

conn = sqlite3.connect(DB)
user, pwd_enc = conn.execute(
    "SELECT ifind_username, ifind_password FROM user_settings WHERE user_id=?", (USER_ID,)
).fetchone()
conn.close()
pwd = decrypt_field(pwd_enc)
rc = iFinDPy.THS_iFinDLogin(user, pwd)
print(f"login rc={rc}")

# ---- THS_RQ 字段探测 (固定 000217.OF) ----
print("\n=== THS_RQ 字段探测 (000217.OF) ===")
rq_fields = [
    "latest",
    "ths_open_fund_net_value",  # 开放式基金单位净值
    "ths_net_value",
    "ths_unit_net_value",
    "ths_nav",
    "ths_open_fund_acc_net_value",  # 累计净值
    "ths_fund_net_value",
    "ths_stock_short_name_stock",
]
for f in rq_fields:
    try:
        d = iFinDPy.THS_RQ("000217.OF", f, "")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        val = None
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            val = df.iloc[0].to_dict()
        print(f"  {f:42s} ec={ec}  val={val}")
    except Exception as e:
        print(f"  {f:42s} EXC {e}")

# ---- thscode 后缀探测 (固定 latest 字段) ----
print("\n=== thscode 后缀探测 (THS_RQ latest) ===")
for ths in ["000217.OF", "000217.OFCN", "000217.OF2", "000217.SH", "000217.SZ", "000217"]:
    try:
        d = iFinDPy.THS_RQ(ths, "latest", "")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        val = None
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            val = df.iloc[0].to_dict()
        print(f"  {ths:14s} ec={ec}  val={val}")
    except Exception as e:
        print(f"  {ths:14s} EXC {e}")

# ---- THS_HQ 字段探测 (000217.OF 近 10 天) ----
print("\n=== THS_HQ 字段探测 (000217.OF, 2026-08-01~2026-08-11) ===")
hq_fields = ["close", "ths_open_fund_net_value", "ths_net_value", "open", "high", "low"]
for f in hq_fields:
    try:
        d = iFinDPy.THS_HQ("000217.OF", f, "CPS:1", "2026-08-01", "2026-08-11")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        n = len(df) if df is not None else 0
        sample = None
        if df is not None and n > 0:
            sample = df.head(2).to_dict("records")
        print(f"  {f:42s} ec={ec}  n={n}  sample={sample}")
    except Exception as e:
        print(f"  {f:42s} EXC {e}")

# ---- THS_BD 基础数据查基金档案 ----
print("\n=== THS_BD 基金档案 (000217.OF) ===")
try:
    bd = iFinDPy.THS_BD("000217.OF", "ths_fund_manager_fund;ths_fund_short_name")
    ec = getattr(bd, "errorcode", "?")
    df = getattr(bd, "data", None)
    print(f"  errorcode={ec}")
    if df is not None:
        print(df.to_string())
except Exception as e:
    print(f"  EXC {e}")

# ---- THS_DS 日期序列 (开放式基金净值可能在 DS 而非 HQ) ----
print("\n=== THS_DS 日期序列 (000217.OF) ===")
try:
    ds = iFinDPy.THS_DS("000217.OF", "ths_open_fund_net_value", "", "2026-08-01", "2026-08-11", "CPS:1")
    ec = getattr(ds, "errorcode", "?")
    df = getattr(ds, "data", None)
    n = len(df) if df is not None else 0
    sample = None
    if df is not None and n > 0:
        sample = df.head(3).to_dict("records")
    print(f"  ths_open_fund_net_value ec={ec} n={n} sample={sample}")
except Exception as e:
    print(f"  EXC {e}")
