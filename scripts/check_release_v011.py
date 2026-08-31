# -*- coding: utf-8 -*-
"""打包 exe 冒烟：模拟收件人注册 → 验证回测面板关键接口全部可用。

用法: python scripts/check_release_v011.py [BASE]  (默认 http://127.0.0.1:8400)
"""
import json
import sys
import time
import urllib.error
import urllib.request

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8400"
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None


def req(method, path, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(B + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if TOKEN:
        r.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with op.open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"_raw": body[:300]}


def auth(action):
    return req("POST", f"/api/auth/{action}",
               {"email": "recipient@test.com", "password": "test123456",
                "name": "收件人"})


ok = True
code, d = auth("register")
if code == 200:
    print("[OK ] register")
else:
    code, d = auth("login")
    print(f"[{'OK ' if code == 200 else 'FAIL'}] register->{code}, login fallback")
ok &= code == 200
TOKEN = d["access_token"]

t0 = time.time()
code, d = req("GET", "/api/research/assets/pooled-count")
good = code == 200 and d.get("count", 0) > 1000
print(f"[{'OK ' if good else 'FAIL'}] pooled-count -> {code} count={d.get('count')} ({time.time()-t0:.2f}s)")
ok &= good

code, groups = req("GET", "/api/research/assets/groups")
good = code == 200 and bool(groups)
print(f"[{'OK ' if good else 'FAIL'}] groups -> {code} n={len(groups) if isinstance(groups, list) else '?'}")
ok &= good

code, strats = req("GET", "/api/strategies")
good = code == 200 and bool(strats)
print(f"[{'OK ' if good else 'FAIL'}] strategies -> {code} n={len(strats) if isinstance(strats, list) else '?'}")
ok &= good

# all_pooled 展开（不真正等待回测跑完，只验证创建路径不再 500）
if strats and groups:
    payload = {"strategy_id": strats[0]["id"], "strategy_version": strats[0].get("version", 1),
               "params": {}, "universe": [], "group_ids": [groups[0]["id"]], "all_pooled": False,
               "start_date": "2024-01-01", "end_date": "2024-03-31", "rebalance_freq": "monthly"}
    code, bt = req("POST", "/api/backtests", payload)
    good = code == 200
    print(f"[{'OK ' if good else 'FAIL'}] POST /backtests (group_ids) -> {code} "
          f"{'' if good else json.dumps(bt, ensure_ascii=False)[:200]}")
    ok &= good
    if good:
        code, items = req("GET", "/api/backtests")
        hit = next((x for x in items if x["id"] == bt["id"]), None) if isinstance(items, list) else None
        good = code == 200 and bool(hit) and bool(hit.get("group_names"))
        print(f"[{'OK ' if good else 'FAIL'}] GET /backtests -> {code} group_names="
              f"{[m['name'] for m in (hit or {}).get('group_names', [])]}")
        ok &= good
        code, det = req("GET", f"/api/backtests/{bt['id']}?parts=core")
        print(f"[{'OK ' if code == 200 else 'FAIL'}] GET /backtests/{{id}}?parts=core -> {code}")
        ok &= code == 200

print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
