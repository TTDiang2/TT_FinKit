"""命门 Task0: 验证 iFinD 对 .OF 场外基金净值的可行性。

验证 4 个关键点:
  1. 凭证从 DB 解密往返成功
  2. THS_iFinDLogin 登录成功
  3. THS_RQ latest 对 .OF 基金返回有效净值 (场外基金一日一净值)
  4. THS_HQ close 对 .OF 基金返回历史净值序列

跑法: python scripts/verify_ifind_of.py   (workdir=backend)
"""
import sys
import os
import sqlite3
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.utils.crypto import decrypt_field
from app.services import ifind_client

USER_ID = "4481a5f7-6e5a-483e-972f-edcfa0f288df"  # TTDiang@outlook.com
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "finkit.db")


def read_creds():
    conn = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(user_settings)").fetchall()]
    print(f"user_settings columns: {cols}")
    row = conn.execute(
        "SELECT ifind_username, ifind_password FROM user_settings WHERE user_id=?",
        (USER_ID,),
    ).fetchone()
    conn.close()
    return row


def main():
    print(f"iFinDPy available: {ifind_client.is_available()}")
    if ifind_client.import_error():
        print(f"  import_error: {ifind_client.import_error()}")

    row = read_creds()
    if not row:
        print("ERROR: user_settings 无此用户行"); return
    user, pwd_enc = row
    if not user:
        print("ERROR: ifind_username 在 DB 为空"); return
    pwd = decrypt_field(pwd_enc or "")
    if not pwd:
        print("ERROR: ifind_password 解密为空 / 解密失败"); return
    print(f"[1] 凭证 OK: user={user}, pwd_len={len(pwd)} (加密往返成功)")

    # 登录
    try:
        ifind_client._login_sync(user, pwd)
        print("[2] 登录 OK")
    except Exception as e:
        print(f"[2] 登录 FAIL: {e}"); return

    # 命门 1: 实时净值 (THS_RQ latest)
    print("\n=== 命门 1: THS_RQ 实时净值 (.OF) ===")
    for sym, label in [
        ("000217", "华安黄金"),
        ("004243", "广发道琼斯石油QDII"),
        ("110001", "易方达平稳"),
        ("017895", "汇添富纳指生物"),
    ]:
        ths = ifind_client.to_thscode(sym, "FUND_CN")
        try:
            price, cn_name = ifind_client._realtime_sync(ths)
            print(f"  OK  {ths} ({label}): latest={price}, name={cn_name}")
        except Exception as e:
            print(f"  FAIL {ths} ({label}): {e}")

    # 命门 2: 历史净值 (THS_HQ close, 近 60 天)
    print("\n=== 命门 2: THS_HQ 历史净值序列 (.OF, 近 60 天) ===")
    end = date.today().strftime("%Y-%m-%d")
    begin = (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
    for sym, label in [("000217", "华安黄金"), ("004243", "广发道琼斯石油QDII")]:
        ths = ifind_client.to_thscode(sym, "FUND_CN")
        try:
            r = ifind_client._history_close_sync(ths, begin, end)
            print(f"  OK  {ths} ({label}): {len(r)} points, range {begin}~{end}")
            if r:
                print(f"       first={r[0]}")
                print(f"       last ={r[-1]}")
        except Exception as e:
            print(f"  FAIL {ths} ({label}): {e}")


if __name__ == "__main__":
    main()
