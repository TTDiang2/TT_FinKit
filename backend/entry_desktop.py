"""PyInstaller entry: run the FastAPI backend as a standalone exe.

Usage: FinKitBackend.exe --host 127.0.0.1 --port 8000
DB paths come from PUBLIC_DATABASE_URL / PRIVATE_DATABASE_URL env vars
(set by the launcher). Defaults keep finkit.db layout for dev runs.
"""
import os
import sys

# PyInstaller onefile 解包目录里才找得到 app 包
sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
