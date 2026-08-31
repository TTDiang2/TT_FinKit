"""Chain: wait for the 7713-pool exposure recompute → final pooling sweep →
refresh asset stats → append results to docs/汇报20260829.md.

Usage (from backend/):  python scripts/finish_batch3.py
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

RECOMPUTE_LOG = BACKEND / "recompute_final2.log"
REPORT = BACKEND.parents[0] / "docs" / "汇报20260829.md"


def recompute_done() -> bool:
    try:
        return "ALL DONE" in RECOMPUTE_LOG.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def wait_recompute(max_hours: float = 5.0) -> None:
    deadline = time.time() + max_hours * 3600
    while time.time() < deadline:
        if recompute_done():
            print("recompute finished", flush=True)
            return
        time.sleep(120)
    print("WARNING: recompute wait timeout", flush=True)


def pooled_count() -> int:
    import sqlite3
    conn = sqlite3.connect(str(BACKEND / "finkit.db"), timeout=30)
    n = conn.execute("SELECT COUNT(*) FROM research_assets WHERE status='pooled'").fetchone()[0]
    conn.close()
    return n


def run_sweep() -> str:
    r = subprocess.run(
        [sys.executable, "scripts/pool_watchlist.py", "--pause", "90"],
        cwd=str(BACKEND), capture_output=True, text=True, timeout=3 * 3600)
    tail = (r.stdout or "")[-300:]
    print(f"sweep rc={r.returncode}: {tail}", flush=True)
    return f"rc={r.returncode}"


def refresh_stats() -> dict:
    from app.services.asset_stats import refresh_stats
    return refresh_stats(str(BACKEND / "finkit.db"))


def append_report(sweep: str, stats: dict) -> None:
    with REPORT.open("a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## 八、终局清扫与因子重算（自动追加于 {time.strftime('%Y-%m-%d %H:%M')}）\n\n")
        f.write("- 全池（7713）因子暴露重算：见 backend/recompute_final2.log\n")
        f.write(f"- 终局入池清扫：{sweep}（明细 pool_watchlist_run6.log + _pool_watchlist_summary.json）\n")
        f.write(f"- research_asset_stats 刷新：{json.dumps(stats, ensure_ascii=False)}\n")
        f.write(f"- 最终入池总数：{pooled_count()}\n")


def _sync_main() -> int:
    wait_recompute()
    time.sleep(10)
    sweep = "skip"
    try:
        sweep = run_sweep()
    except Exception as e:  # noqa: BLE001
        sweep = f"failed {type(e).__name__}: {e}"
    stats: dict = {}
    try:
        stats = refresh_stats()
    except Exception as e:  # noqa: BLE001
        stats = {"error": str(e)}
    try:
        append_report(sweep, stats)
    except Exception as e:  # noqa: BLE001
        print("report append failed:", e, flush=True)
    print("CHAIN DONE", flush=True)
    return 0


if __name__ == "__main__":
    print("chain start", time.strftime("%H:%M"), flush=True)
    raise SystemExit(_sync_main())
