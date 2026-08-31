"""矩阵端点调试（临时）— 写文件而非 logger，彻底绕开控制台归属问题。"""
from datetime import datetime
from pathlib import Path

DEBUG_FILE = Path(__file__).resolve().parents[1] / "matrix_debug.log"


def debug_log(msg: str) -> None:
    with open(DEBUG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")
