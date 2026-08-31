"""Refresh research_asset_stats (per-asset windows over the full price scan).

幂等：全量重算覆盖。入池/拉数后跑一次；UI 统计页与排序读该表。
Usage (from backend/):  python scripts/refresh_asset_stats.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.asset_stats import refresh_stats  # noqa: E402

if __name__ == "__main__":
    t0 = time.time()
    r = refresh_stats("finkit.db")
    print(f"stats refreshed: {r} (total {time.time()-t0:.0f}s)")
