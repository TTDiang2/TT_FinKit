# -*- coding: utf-8 -*-
"""回测面板修复冒烟（HTTP 模式，打指定端口的后端实例）：

修复点回归验证：
1. GET /api/research/assets/pooled-count —— 新轻量计数端点（毫秒级）
2. GET /api/backtests —— group_ids 非空时 _resolve_group_meta 改走 public 库，
   不再 no such table 500
3. GET /api/backtests/{id}?parts=core —— 补上 pub 依赖，不再 NameError 500

不注册新用户：直接取 private 库最早注册的主用户并自造 JWT。

用法: python scripts/check_backtest_panel.py [BASE]  (默认 http://127.0.0.1:8300)
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

PRIVATE_DB = ROOT / "backend" / "finkit_private.db"
PUBLIC_DB = ROOT / "backend" / "finkit_public.db"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8300"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

TOKEN = None


def req(method: str, path: str, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if TOKEN:
        r.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with opener.open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"_raw": body[:300]}


def main_user_id() -> str:
    con = sqlite3.connect(PRIVATE_DB)
    try:
        row = con.execute(
            "SELECT id FROM users ORDER BY created_at ASC LIMIT 1").fetchone()
        if not row:
            raise SystemExit("private 库没有任何用户")
        return row[0]
    finally:
        con.close()


def main() -> int:
    global TOKEN
    from app.utils.security import create_access_token
    uid = main_user_id()
    TOKEN = create_access_token({"sub": uid})
    ok = True

    # 1) 轻量计数端点（计时验证不再分钟级）
    t0 = time.time()
    code, data = req("GET", "/api/research/assets/pooled-count")
    dt = time.time() - t0
    cnt = data.get("count") if isinstance(data, dict) else None
    good = code == 200 and cnt
    print(f"[{'OK ' if good else 'FAIL'}] pooled-count -> {code} count={cnt} ({dt:.2f}s)")
    ok &= bool(good)

    # 2) 组合列表
    code, groups = req("GET", "/api/research/assets/groups")
    good = code == 200 and groups
    print(f"[{'OK ' if good else 'FAIL'}] groups -> {code} n={len(groups) if isinstance(groups, list) else '?'}")
    ok &= bool(good)
    if not groups:
        print("RESULT: FAIL (无组合)")
        return 1

    # 3) 新建一条带 group_ids 的回测：选「展开后确有 pooled 成员」的最小组合
    con = sqlite3.connect(PUBLIC_DB)
    try:
        rows = con.execute(
            "SELECT m.group_id, COUNT(*) FROM research_group_members m "
            "JOIN research_assets a ON a.id = m.asset_id "
            "WHERE a.status = 'pooled' GROUP BY m.group_id").fetchall()
    finally:
        con.close()
    pooled_n = {gid: n for gid, n in rows}
    candidates = [g for g in groups if pooled_n.get(g["id"])]
    if not candidates:
        print("[FAIL] 所有组合都没有已入池成员，无法构造 group_ids 回测")
        return 1
    g = min(candidates, key=lambda x: pooled_n[x["id"]])
    code, strats = req("GET", "/api/strategies")
    if code != 200 or not strats:
        print(f"[FAIL] strategies -> {code}")
        return 1
    payload = {
        "strategy_id": strats[0]["id"], "strategy_version": strats[0].get("version", 1),
        "params": {}, "universe": [], "group_ids": [g["id"]], "all_pooled": False,
        "start_date": "2024-01-01", "end_date": "2024-03-31",
        "rebalance_freq": "monthly",
    }
    code, bt = req("POST", "/api/backtests", payload)
    good = code == 200
    print(f"[{'OK ' if good else 'FAIL'}] POST /backtests (group_ids=[{g['name']}]) "
          f"-> {code} {'' if good else json.dumps(bt, ensure_ascii=False)[:200]}")
    if not good:
        return 1
    bt_id = bt["id"]

    # 4) 列表（此前 group_ids 非空即 500：no such table: research_groups）
    code, items = req("GET", "/api/backtests")
    hit = next((x for x in items if x["id"] == bt_id), None) if isinstance(items, list) else None
    good = code == 200 and hit and hit.get("group_names")
    names = [m["name"] for m in (hit or {}).get("group_names", [])]
    print(f"[{'OK ' if good else 'FAIL'}] GET /backtests -> {code} "
          f"n={len(items) if isinstance(items, list) else '?'} group_names={names}")
    ok &= bool(good)

    # 5) 详情 core（此前 pub 未定义 -> NameError 500）
    code, detail = req("GET", f"/api/backtests/{bt_id}?parts=core")
    good = code == 200
    print(f"[{'OK ' if good else 'FAIL'}] GET /backtests/{{id}}?parts=core -> {code} "
          f"{'' if good else json.dumps(detail, ensure_ascii=False)[:200]}")
    ok &= good

    # 6) 全部入池标的路径（all_pooled=True 展开，仅验证展开不报 500，立即删除）
    payload2 = dict(payload, all_pooled=True, group_ids=[])
    code, bt2 = req("POST", "/api/backtests", payload2)
    n_univ = len(bt2.get("universe") or []) if code == 200 else -1
    print(f"[{'OK ' if code == 200 and n_univ > 0 else 'FAIL'}] POST /backtests "
          f"(all_pooled=True) -> {code} universe={n_univ}")
    ok &= code == 200 and n_univ > 0
    if code == 200:
        c2, _ = req("DELETE", f"/api/backtests/{bt2['id']}")
        print(f"       cleanup all_pooled 回测 -> {c2}")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
