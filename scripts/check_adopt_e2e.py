# -*- coding: utf-8 -*-
"""模拟收件人：注册新账号 → 验证 public 数据认领后标的/组合可见。"""
import json
import sys
import urllib.error
import urllib.request

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8300"
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def auth(action):
    req = urllib.request.Request(
        B + "/api/auth/" + action,
        data=json.dumps({"email": "recipient@test.com", "password": "test123456",
                         "name": "收件人"}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(op.open(req, timeout=30).read())["access_token"]

try:
    tok = auth("register")
    print("registered, token ok")
except urllib.error.HTTPError as e:
    print("register ->", e.code, e.read().decode("utf-8", "replace")[:120])
    tok = auth("login")
    print("logged in instead, token ok")

h = {"Authorization": "Bearer " + tok}
import time
t0 = time.time()
r = op.open(urllib.request.Request(
    B + "/api/research/assets?page=1&page_size=50", headers=h), timeout=60)
d = json.loads(r.read())
n = d.get("total") if isinstance(d, dict) else -1
first = d.get("items", [{}])[0].get("symbol", "?") if isinstance(d, dict) and d.get("items") else "?"
print(f"标的分页 -> {r.status} total = {n} 首只 = {first} ({time.time()-t0:.1f}s)")
assert isinstance(n, int) and n > 10000, f"标的数量异常: {n}"

t0 = time.time()
r = op.open(urllib.request.Request(B + "/api/research/assets/selector", headers=h), timeout=120)
d = json.loads(r.read())
n = len(d.get("items", [])) if isinstance(d, dict) else len(d)
print(f"选择器 -> {r.status} count = {n} ({time.time()-t0:.1f}s)")
assert n > 10000, f"选择器数量异常: {n}"

t0 = time.time()
r = op.open(urllib.request.Request(B + "/api/research/assets/groups", headers=h), timeout=60)
g = json.loads(r.read())
ng = len(g) if isinstance(g, list) else len(g.get("items", []))
print(f"组合 -> {r.status} count = {ng} ({time.time()-t0:.1f}s)")
assert ng > 0, "组合为空"
print("ADOPT E2E PASSED")
