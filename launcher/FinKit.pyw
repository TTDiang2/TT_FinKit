# -*- coding: utf-8 -*-
"""
FinKit Desktop Launcher (silent).

Runs without any console window (invoke via pythonw.exe / .pyw).
1. Start backend (FastAPI on 127.0.0.1:8000) hidden if not already running
2. Wait for the health check
3. Launch the Pake-packaged FinKit.exe
4. When the app closes, stop the backend we started
"""
import ctypes
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent.parent           # build/desktop -> build -> FinKit
BACKEND_DIR = ROOT / "backend"
EXE = APP_DIR / "FinKit.exe"
PORT = 8000
HEALTH_URL = f"http://127.0.0.1:{PORT}/api/health"
LOG_FILE = APP_DIR / "backend.log"

# release 布局检测: APP_DIR/backend/FinKitBackend.exe + APP_DIR/data/
BACKEND_EXE = APP_DIR / "backend" / "FinKitBackend.exe"
DATA_DIR = APP_DIR / "data"
IS_RELEASE = BACKEND_EXE.exists() and DATA_DIR.exists()

if IS_RELEASE:
    # 数据库指向 data/ 下的双库文件；private.db 首次启动由后端 create_all 自动生成空库
    os.environ.setdefault("PUBLIC_DATABASE_URL", f"sqlite+aiosqlite:///{(DATA_DIR / 'finkit_public.db').as_posix()}")
    os.environ.setdefault("PRIVATE_DATABASE_URL", f"sqlite+aiosqlite:///{(DATA_DIR / 'finkit_private.db').as_posix()}")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def msgbox(title, text):
    ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR


def health_ok():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    if not EXE.exists():
        msgbox("FinKit", f"找不到 FinKit.exe:\n{EXE}\n\n请先运行打包命令。")
        return

    backend_proc = None

    # 1. ensure backend is running (reuse an existing one, e.g. dev server)
    if not health_ok():
        try:
            with open(LOG_FILE, "ab") as log:
                if IS_RELEASE:
                    backend_proc = subprocess.Popen(
                        [str(BACKEND_EXE), "--host", "127.0.0.1", "--port", str(PORT)],
                        cwd=str(APP_DIR),
                        stdout=log, stderr=subprocess.STDOUT,
                        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                    )
                else:
                    backend_proc = subprocess.Popen(
                        [sys.executable, "-m", "uvicorn", "app.main:app",
                         "--host", "127.0.0.1", "--port", str(PORT)],
                        cwd=str(BACKEND_DIR),
                        stdout=log, stderr=subprocess.STDOUT,
                        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                    )
        except Exception as e:
            msgbox("FinKit", f"启动后端失败:\n{e}")
            return

        # 2. wait for the health check (max 30s)
        for _ in range(30):
            if health_ok():
                break
            time.sleep(1)
        if not health_ok():
            msgbox("FinKit",
                   f"后端启动超时 (http://127.0.0.1:{PORT})。\n"
                   f"详见 {LOG_FILE}")
            if backend_proc is not None:
                subprocess.run(["taskkill", "/PID", str(backend_proc.pid),
                                "/T", "/F"], capture_output=True)
            return

    # 3. launch the app and wait for it to close
    subprocess.run([str(EXE)])

    # 4. stop the backend we started (tree-kill to catch any children)
    if backend_proc is not None:
        subprocess.run(["taskkill", "/PID", str(backend_proc.pid),
                        "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    main()
