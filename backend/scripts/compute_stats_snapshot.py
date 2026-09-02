"""Standalone stats-snapshot compute — 子进程入口（开发态）。

计算逻辑统一在 app/services/stats_compute.py（frozen 态直接 to_thread 调它），
本脚本只是让开发态能把纯 Python 大循环挪出后端进程。

Usage: python scripts/compute_stats_snapshot.py <days> <assets_or_all> <user_id>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.stats_compute import main  # noqa: E402

if __name__ == "__main__":
    main()
