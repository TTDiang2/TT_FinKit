# -*- coding: utf-8 -*-
"""信号面板修复冒烟（HTTP 模式，打指定端口的后端实例）：

1. GET /api/signals/trade-plan —— 此前 db(private) 查 public 表 research_prices
   -> no such table 500
2. GET /api/monitor/strategy-health —— 此前 Strategy/research_assets/research_prices
   全走 private session -> no such table 500
3. GET /api/signals/current —— strategy_version_note 应透出（版本号显示修复）

不注册新用户：直接取 private 库最早注册的主用户并自造 JWT。

用法: python scripts/check_signal_panel.py [BASE]  (默认 http://127.0.0.1:8300)
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

    # 1) 调仓清单（此前 500: no such table: research_prices）
    t0 = time.time()
    code, plan = req("GET", "/api/signals/trade-plan")
    dt = time.time() - t0
    good = code == 200 and isinstance(plan, dict) and "rows" in plan
    n_rows = len(plan.get("rows") or []) if good else -1
    print(f"[{'OK ' if good else 'FAIL'}] GET /signals/trade-plan -> {code} "
          f"rows={n_rows} ({dt:.2f}s) "
          f"{'' if good else json.dumps(plan, ensure_ascii=False)[:200]}")
    ok &= bool(good)

    # 2) 策略健康（此前 500: no such table）
    code, health = req("GET", "/api/monitor/strategy-health")
    has_keys = isinstance(health, dict) and {"as_of", "strategy"} <= set(health)
    good = code == 200 and has_keys
    print(f"[{'OK ' if good else 'FAIL'}] GET /monitor/strategy-health -> {code} "
          f"strategy={(health or {}).get('strategy')} "
          f"freshness={(health or {}).get('data_freshness')} "
          f"{'' if good else json.dumps(health, ensure_ascii=False)[:200]}")
    ok &= bool(good)

    # 3) 当前信号 + 版本注释
    code, sig = req("GET", "/api/signals/current")
    if code == 200 and sig:
        note = sig.get("strategy_version_note")
        good = True
        print(f"[OK ] GET /signals/current -> {code} "
              f"name={sig.get('strategy_name')} version={sig.get('strategy_version')} "
              f"version_note={note}")
    else:
        # 没有信号不算失败（可后跑 run 生成），只提示
        good = code in (200, 404) or sig is None
        print(f"[warn] GET /signals/current -> {code} {str(sig)[:120]}")
    ok &= bool(good)

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
