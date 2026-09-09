"""Refresh research_asset_stats (per-asset windows over the full price scan).

幂等：全量重算覆盖。入池/拉数后跑一次；UI 统计页与排序读该表。
Usage (from backend/):  python scripts/refresh_asset_stats.py [db_path]

db_path 省略时按双库配置解析 public 库（public_db_path()）。此前写死
"finkit.db" 在拆分双库后指向一个空文件，导致脚本必然 no such table 报错、
派生表长期不更新（标的页"最新数据"停在旧日期）。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import public_db_path  # noqa: E402
from app.services.asset_stats import refresh_stats  # noqa: E402

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else public_db_path()
    t0 = time.time()
    print(f"[db] {db}")
    r = refresh_stats(db)
    print(f"stats refreshed: {r} (total {time.time()-t0:.0f}s)")
