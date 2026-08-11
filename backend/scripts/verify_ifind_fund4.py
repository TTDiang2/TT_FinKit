"""命门诊断 4: 查 -209 含义 + 股票对照（确认账号权限范围）+ 基金最基础指标。"""
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

print("=== 错误码解释 ===")
for ec in [-209, -4001, -2, -201, -1]:
    try:
        info = iFinDPy.THS_GetErrorInfo(ec, "")
        print(f"  {ec}: {info}")
    except Exception as e:
        print(f"  {ec}: 查询异常 {e}")

print("\n=== 股票对照（验证账号权限范围）===")
for ths, label in [("600519.SH", "贵州茅台"), ("000001.SZ", "平安银行")]:
    try:
        d = iFinDPy.THS_RQ(ths, "latest;ths_stock_short_name_stock", "")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        val = df.iloc[0].to_dict() if df is not None and hasattr(df, "iloc") and len(df) > 0 else None
        print(f"  RQ {ths}({label}): ec={ec}, val={val}")
    except Exception as e:
        print(f"  RQ {ths}: {e}")
    try:
        d = iFinDPy.THS_HQ(ths, "close", "CPS:1", "2026-07-01", "2026-07-31")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        n = len(df) if df is not None and hasattr(df, "__len__") else 0
        print(f"  HQ {ths}({label}): ec={ec}, {n} 条")
    except Exception as e:
        print(f"  HQ {ths}: {e}")

print("\n=== 基金最基础指标（基金名称/类型）===")
for ind in ["ths_fund_short_name", "ths_fund_manager_fund", "ths_fund_type_fund", "ths_fund_setupdate_fund"]:
    try:
        d = iFinDPy.THS_BD("000217.OF", ind, "")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        val = df.iloc[0, -1] if df is not None and hasattr(df, "iloc") and len(df) > 0 else None
        print(f"  BD 000217.OF {ind}: ec={ec}, val={val}")
    except Exception as e:
        print(f"  BD {ind}: {e}")

# 试 ETF (场内基金 518880 黄金ETF) 对照——如果有数据说明账号有 ETF 权限但无场外基金权限
print("\n=== 场内 ETF 对照（518880.SH 黄金ETF）===")
try:
    d = iFinDPy.THS_RQ("518880.SH", "latest;ths_stock_short_name_stock", "")
    ec = getattr(d, "errorcode", "?")
    df = getattr(d, "data", None)
    val = df.iloc[0].to_dict() if df is not None and hasattr(df, "iloc") and len(df) > 0 else None
    print(f"  RQ 518880.SH: ec={ec}, val={val}")
except Exception as e:
    print(f"  RQ 518880.SH: {e}")

print("\n=== 诊断 4 完成 ===")
