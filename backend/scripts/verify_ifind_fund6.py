"""命门诊断 6: 确认 ths_unit_nv_fund 能拉历史净值序列 + 找累计净值指标。

关键验证: THS_DS(thscode, "ths_unit_nv_fund", ...) 能否返回历史日净值序列。
这是迁移功能（反推份额）的核心依赖。
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

FUNDS = [
    ("000217.OF", "华安黄金"),
    ("004243.OF", "广发道琼斯石油"),
    ("110001.OF", "易方达平稳"),
    ("017895.OF", "汇添富纳指生物"),
]

# ---- 1. THS_DS 拉历史净值序列（关键！）----
print("=== THS_DS ths_unit_nv_fund 历史日净值（2026-07）===")
history_ok = 0
for ths, name in FUNDS:
    try:
        d = iFinDPy.THS_DS(ths, "ths_unit_nv_fund", "", "", "2026-07-01", "2026-07-31")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        cnt = len(df) if df is not None and hasattr(df, "__len__") else 0
        sample = None
        if df is not None and hasattr(df, "head") and cnt > 0:
            sample = df.head(2).to_dict("records")
            tail = df.tail(1).to_dict("records")
        else:
            tail = None
        marker = "✓" if ec == 0 and cnt > 0 else "✗"
        print(f"  {marker} {ths}({name}): ec={ec}, {cnt} 条")
        if sample:
            print(f"      首: {sample[0]}")
        if tail:
            print(f"      末: {tail[0]}")
        if ec == 0 and cnt > 0:
            history_ok += 1
    except Exception as e:
        print(f"  ✗ {ths}({name}): 异常 {e}")

# ---- 2. 累计净值指标名 ----
print(f"\n=== 累计净值指标名 (000217.OF) ===")
acc_candidates = [
    "ths_acc_nv_fund",
    "ths_total_nv_fund",
    "ths_accumulated_nv_fund",
    "ths_acc_unit_nv_fund",
    "ths_nav_acc_fund",
    "ths_unit_acc_nv_fund",
]
acc_indicator = None
for ind in acc_candidates:
    try:
        d = iFinDPy.THS_BD("000217.OF", ind, "")
        ec = getattr(d, "errorcode", "?")
        df = getattr(d, "data", None)
        val = None
        if df is not None and hasattr(df, "iloc") and len(df) > 0:
            val = df.iloc[0, -1] if df.shape[1] >= 1 else None
        marker = "✓" if ec == 0 and val is not None else " "
        print(f"  {marker} {ind:42s}: ec={ec}, val={val}")
        if ec == 0 and val is not None and not acc_indicator:
            acc_indicator = ind
    except Exception as e:
        print(f"    {ind}: 异常 {e}")

# ---- 3. 汇总 ----
print(f"\n=== 命门最终结论 ===")
print(f"单位净值指标: ths_unit_nv_fund")
print(f"累计净值指标: {acc_indicator or '(未找到，需查文档)'}")
print(f"THS_DS 历史净值: {history_ok}/{len(FUNDS)} 基金成功")
if history_ok == len(FUNDS):
    print("✓✓✓ 命门完全通过！迁移功能用 iFinD + ths_unit_nv_fund 反推份额")
elif history_ok > 0:
    print(f"⚠ {history_ok} 只成功 — 看具体哪些基金不支持")
else:
    print("✗ THS_DS 不可行 — 需要其他方案")

print("\n=== 诊断 6 完成 ===")
