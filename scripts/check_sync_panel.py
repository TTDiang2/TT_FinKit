# -*- coding: utf-8 -*-
"""设置页私有库同步端点冒烟（HTTP，打 8300）：

1. GET  /api/sync/config  —— 配置读取（token 脱敏）
2. PUT  /api/sync/config  —— 首次配置缺 token 应 400；带 token 保存成功
3. GET  /api/sync/config  —— 保存后 repo/token_tail 生效
4. GET  /api/sync/remote   —— 未配置/假 token 时应 400/502（不能 500）
5. POST /api/sync/push     —— 假 token 应 400/502（不能 500）

用法: python scripts/check_sync_panel.py [BASE] (默认 http://127.0.0.1:8300)
"""
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
PRIVATE_DB = ROOT / "backend" / "finkit_private.db"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8300"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None


def req(method: str, path: str, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if TOKEN:
        r.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with opener.open(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}


def main() -> int:
    global TOKEN
    from app.utils.security import create_access_token
    uid = sqlite3.connect(PRIVATE_DB).execute(
        "SELECT id FROM users ORDER BY created_at ASC LIMIT 1").fetchone()[0]
    TOKEN = create_access_token({"sub": uid})
    ok = True

    code, cfg = req("GET", "/api/sync/config")
    good = code == 200 and "repo" in cfg and "token_set" in cfg
    print(f"[{'OK ' if good else 'FAIL'}] GET /sync/config -> {code} repo={cfg.get('repo')!r} "
          f"token_set={cfg.get('token_set')} db={cfg.get('private_db')}")
    ok &= good

    code, r = req("PUT", "/api/sync/config", {"repo": "demo/repo", "tag": "db-snapshot", "token": None})
    good = code == 400  # 首次配置必须给 token
    print(f"[{'OK ' if good else 'FAIL'}] PUT /sync/config (no token) -> {code} {r}")
    ok &= good

    code, r = req("PUT", "/api/sync/config", {"repo": "demo/repo", "tag": "db-snapshot", "token": "ghp_test_1234567890"})
    good = code == 200 and r.get("repo") == "demo/repo" and r.get("token_tail") == "7890"
    print(f"[{'OK ' if good else 'FAIL'}] PUT /sync/config (with token) -> {code} repo={r.get('repo')} tail={r.get('token_tail')}")
    ok &= good

    code, r = req("GET", "/api/sync/remote")
    good = code in (400, 502)  # 假 token：400(ValueError)/502(GitHub 拒绝)，绝不能 500
    print(f"[{'OK ' if good else 'FAIL'}] GET /sync/remote (fake token) -> {code} {r}")
    ok &= good

    code, r = req("POST", "/api/sync/push")
    good = code in (400, 502)
    print(f"[{'OK ' if good else 'FAIL'}] POST /sync/push (fake token) -> {code} {str(r)[:120]}")
    ok &= good

    # 恢复：清掉测试配置，避免污染真实使用
    cfg_path = Path(str(cfg.get("private_db") or "")).parent / "sync_config.json"
    if cfg_path.exists():
        cfg_path.unlink()
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
