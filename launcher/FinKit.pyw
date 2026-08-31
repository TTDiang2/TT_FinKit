# -*- coding: utf-8 -*-
"""
FinKit Desktop Launcher (silent).

Runs without any console window (invoke via pythonw.exe / .pyw).

1. Start the backend on 127.0.0.1:8100 (hidden) if it isn't already up
2. Wait for /api/health
3. Launch FinKit.exe (desktop shell — it opens http://127.0.0.1:8100)
4. When the shell closes, stop the backend *only if we started it*

PORT 必须与桌面壳 FinKit.exe 里内嵌的地址一致（8100），否则窗口一打开
就是「127.0.0.1 拒绝连接」。改端口要同步重新打包 FinKit.exe。
"""
import ctypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent.parent           # build/desktop -> build -> FinKit
BACKEND_DIR = ROOT / "backend"
EXE = APP_DIR / "FinKit.exe"
PORT = 8100
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

# onefile 的 exe 首次启动要解包 200MB+，慢机器上可能要 1 分钟以上
STARTUP_TIMEOUT = 120


def msgbox(title, text):
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [launcher] {msg}\n")
    except Exception:
        pass


def health_ok():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def log_tail(n=25):
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return "(无日志)"


def main():
    if not EXE.exists():
        msgbox("FinKit", f"找不到 FinKit.exe:\n{EXE}")
        return

    log(f"start | release={IS_RELEASE} port={PORT}")

    backend_proc = None

    # 1. ensure backend is running (reuse an existing one, e.g. dev server)
    if not health_ok():
        try:
            with open(LOG_FILE, "ab") as logf:
                if IS_RELEASE:
                    cmd = [str(BACKEND_EXE), "--host", "127.0.0.1", "--port", str(PORT)]
                    cwd = str(APP_DIR)
                else:
                    cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
                           "--host", "127.0.0.1", "--port", str(PORT)]
                    cwd = str(BACKEND_DIR)
                log("spawn: " + " ".join(cmd))
                backend_proc = subprocess.Popen(
                    cmd, cwd=cwd,
                    stdout=logf, stderr=subprocess.STDOUT,
                    creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                )
        except Exception as e:
            log(f"spawn failed: {e}")
            msgbox("FinKit", f"启动后端失败:\n{e}")
            return

        # 2. wait for the health check (exe 首次解包很慢，给足时间)
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            if health_ok():
                break
            if backend_proc.poll() is not None:
                # 进程已经退出 —— 必崩，直接把日志尾部弹出来
                log("backend exited early, rc=" + str(backend_proc.returncode))
                msgbox("FinKit",
                       f"后端启动失败（端口 {PORT}）。\n\n"
                       f"日志尾部：\n{log_tail()}")
                return
            time.sleep(1)

        if not health_ok():
            log("startup timeout")
            msgbox("FinKit",
                   f"后端启动超时（{STARTUP_TIMEOUT}s，http://127.0.0.1:{PORT}）。\n\n"
                   f"日志尾部：\n{log_tail()}")
            if backend_proc is not None:
                subprocess.run(["taskkill", "/PID", str(backend_proc.pid),
                                "/T", "/F"], capture_output=True)
            return

    log("backend healthy")

    # 3. launch the app and wait for it to close
    subprocess.run([str(EXE)])
    log("frontend shell closed")

    # 4. stop the backend we started (tree-kill to catch any children)
    if backend_proc is not None:
        subprocess.run(["taskkill", "/PID", str(backend_proc.pid),
                        "/T", "/F"], capture_output=True)
        log("backend stopped")


if __name__ == "__main__":
    main()
