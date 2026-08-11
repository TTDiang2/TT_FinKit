"""命门 Task0: 验证 iFinD 对 .OF 场外基金净值可行性。

结论决定 P0 迁移功能的实现路线：
  - 能取 → 迁移功能用 iFinD 反推份额
  - 不能 → 降级方案（手动输入当日净值 / 接入天天基金）
"""
import sys, os, io, sqlite3
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
# 让 import app 可达（backend 根在 path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.crypto import decrypt_field
import iFinDPy

DB = r"finkit.db"
USER_ID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"  # TTDiang@outlook.com

# ---------- 读凭证 ----------
conn = sqlite3.connect(DB)
row = conn.execute(
    "SELECT ifind_username, ifind_password FROM user_settings WHERE user_id = ?",
    (USER_ID,),
).fetchone()
conn.close()

if not row:
    print("ERROR: 该用户在 user_settings 表无记录"); sys.exit(1)
ifind_user, ifind_pwd_enc = row
if not ifind_user or not ifind_pwd_enc:
    print("ERROR: ifind 账号或密码为空（未配置凭证）"); sys.exit(1)

try:
    ifind_pwd = decrypt_field(ifind_pwd_enc)
except Exception as e:
    print(f"ERROR: 解密密码失败: {e}"); sys.exit(1)

print(f"=== 凭证 ===")
print(f"账号: {ifind_user}")
print(f"密码: {'*' * len(ifind_pwd)} ({len(ifind_pwd)} 字符，解密成功)")

# ---------- 登录 ----------
print(f"\n=== 登录 iFinD ===")
rc = iFinDPy.THS_iFinDLogin(ifind_user, ifind_pwd)
print(f"登录返回码: {rc}  (0=成功, -201=重复登录也算OK, -2=密码错)")
if rc not in (0, -201):
    print(f"❌ 登录失败 — 命门未通过（凭证无效或服务异常）"); sys.exit(1)

# ---------- Task0 主体: 拉 000217.OF 华安黄金 2024 年净值 ----------
print(f"\n=== Task0: THS_HQ 000217.OF 华安黄金 2024 年单位净值 ===")
data = iFinDPy.THS_HQ('000217.OF', 'close', 'CPS:1', '2024-01-01', '2024-12-31')
print(f"errorcode: {data.errorcode}")
if data.errorcode != 0:
    print(f"❌ .OF 净值不可取！错误码: {data.errorcode}")
    print("→ 降级方案: 迁移向导改为用户手动输入当日净值，或接入天天基金 api.fund.eastmoney.com")
else:
    df = data.data
    print(f"✅ 成功！返回 {len(df)} 个交易日净值")
    if df is not None and len(df) > 0:
        print(f"\n首 3 行:")
        print(df.head(3).to_string())
        print(f"\n末 3 行:")
        print(df.tail(3).to_string())
        # 净值范围合理性（华安黄金 000217 应在 1.x 元）
        close_col = df.iloc[:, -1] if df.shape[1] >= 1 else None
        if close_col is not None:
            print(f"\n净值范围: {close_col.min():.4f} ~ {close_col.max():.4f}")
        print(f"\n→ 命门通过！迁移功能用 iFinD 反推份额")

# ---------- Task0 Step4: THS_BD 基金档案（P1 探路，非阻塞）----------
print(f"\n=== Task0 Step4 (P1 探路): THS_BD 基金档案 ===")
try:
    bd = iFinDPy.THS_BD('000217.OF', 'ths_fund_manager_fund;ths_fund_scale_fund')
    print(f"errorcode: {bd.errorcode}")
    if bd.errorcode == 0 and bd.data is not None:
        print(bd.data.to_string())
    else:
        print(f"基金档案不可取（P1 非阻塞，后续再处理）")
except Exception as e:
    print(f"THS_BD 异常: {e}")

try:
    iFinDPy.THS_iFinDLogout()
except Exception:
    pass
print("\n=== 命门验证完成 ===")
