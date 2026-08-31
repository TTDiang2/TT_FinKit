# -*- coding: utf-8 -*-
"""双库模式冒烟：跨 public/private 的核心接口一起探一遍。"""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 401/403 = 需要登录，说明路由通了、只是没带 token，不算双库故障
AUTH_ONLY = {"/api/research/assets/groups", "/api/research/assets"}

CHECKS = [
    ("/api/health", "private/health"),
    ("/api/strategies", "public 策略"),
    ("/api/research/assets/groups", "public 组合"),
    ("/api/factors", "public 因子"),
    ("/api/backtests", "private 回测"),
    ("/api/signals", "private 信号"),
]

ok = True
for path, label in CHECKS:
    try:
        with opener.open(BASE + path, timeout=20) as r:
            body = r.read()
            code = r.status
        body_txt = body.decode("utf-8", "replace")
        try:
            data = json.loads(body)
            n = len(data) if isinstance(data, list) else "-"
        except Exception:
            n = "-"
        except urllib.error.HTTPError as e:
            code = e.code
            body_txt = e.read().decode("utf-8", "replace")
            n = "-"
        except Exception as e:
            ok = False
            print(f"FAIL ---  {label:<16} {path}   {e}")
            continue

        if code == 200:
            flag = "OK "
        elif code in (401, 403) and path.split("?")[0] in AUTH_ONLY:
            flag = "OK*"
        else:
            flag = "FAIL"
            ok = False
        detail = "" if flag == "OK " else f"  <- {body_txt[:80]}"
        print(f"{flag} {code}  {label:<16} {path}   items={n}{detail}")
    except Exception as e:
        ok = False
        print(f"FAIL ---  {label:<16} {path}   {e}")

# 入池标的数（public）
try:
    with opener.open(BASE + "/api/research/assets?status=pooled", timeout=60) as r:
        d = json.loads(r.read())
    print(f"OK  200  public 入池标的      count={len(d)}")
except Exception as e:
    ok = False
    print("FAIL 入池标的:", e)

print("\nRESULT:", "ALL OK" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
