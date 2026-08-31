"""Assemble the FinKit release directory (user picked PyInstaller path).

Produces release/FinKit-vX.Y.Z/ containing:
  FinKit.exe              Pake frontend shell (from build/desktop)
  FinKit.pyw              launcher (dual mode: backend.exe or dev python)
  FinKit-Desktop.bat      double-click entry
  backend/FinKitBackend.exe   PyInstaller-packed API server
  data/finkit_public.db   pre-filled public DB (assets/factors/strategies)
  README.txt              first-run notes

The user's private DB (finkit_private.db) is created EMPTY on first launch —
it never ships.

Usage (from repo root):
  python backend/scripts/build_release.py --version 0.1.0
Requires: pyinstaller installed; frontend/dist built; backend/finkit_public.db
generated via scripts/migrate_to_split_db.py (or fetched from Releases).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DESKTOP = ROOT / "build" / "desktop"
RELEASE = ROOT / "release"


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def build_backend_exe(out_dir: Path) -> None:
    entry = BACKEND / "entry_desktop.py"
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", "FinKitBackend",
        "--distpath", str(out_dir),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build" / "pyinstaller"),
        "--collect-all", "app",
        "--collect-all", "uvicorn",
        "--collect-all", "finkit_strategy",
        "--hidden-import", "aiosqlite",
        "--hidden-import", "PyJWT",
        str(entry),
    ], cwd=str(BACKEND))


def assemble(version: str, skip_backend_build: bool = False) -> Path:
    dest = RELEASE / f"FinKit-v{version}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    backend_out = dest / "backend"
    backend_out.mkdir()
    if skip_backend_build:
        prev = RELEASE / "FinKitBackend.exe"
        if not prev.exists():
            raise SystemExit("--skip-backend-build: 找不到 release/FinKitBackend.exe（先手动打包一次）")
        shutil.copy2(prev, backend_out / "FinKitBackend.exe")
    else:
        build_backend_exe(backend_out)

    # frontend shell + launcher
    shutil.copy2(DESKTOP / "FinKit.exe", dest / "FinKit.exe")
    shutil.copy2(DESKTOP / "FinKit-Desktop.bat", dest / "FinKit-Desktop.bat")
    launcher_src = (DESKTOP / "FinKit.pyw")
    shutil.copy2(launcher_src, dest / "FinKit.pyw")

    # public db 模板
    pub_src = BACKEND / "finkit_public.db"
    if not pub_src.exists():
        raise SystemExit("缺 finkit_public.db——先跑 scripts/migrate_to_split_db.py 生成")
    data = dest / "data"
    data.mkdir()
    shutil.copy2(pub_src, data / "finkit_public.db")

    readme = dest / "README.txt"
    readme.write_text(
        "FinKit — 首次使用\n"
        "================\n"
        "1. 双击 FinKit-Desktop.bat（或 FinKit.pyw）。\n"
        "2. 首次启动自动创建空白数据库 data/finkit_private.db，注册你的账号即可。\n"
        "3. data/finkit_public.db 内置标的池/因子/策略骨架，请勿手改。\n\n"
        "你的个人数据（交易/持仓/回测）只存在于本机 data/finkit_private.db，\n"
        "不会随任何更新包外发。\n",
        encoding="utf-8",
    )
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--skip-backend-build", action="store_true",
                    help="复用已打包的 FinKitBackend.exe")
    args = ap.parse_args()

    if not FRONTEND_DIST.is_dir():
        raise SystemExit("frontend/dist 不存在——先 npm run build")
    if not (DESKTOP / "FinKit.exe").exists():
        raise SystemExit("build/desktop/FinKit.exe 不存在——先跑 Pake 打包")

    dest = assemble(args.version, skip_backend_build=args.skip_backend_build)
    print(f"\n[release] assembled: {dest}")
    print("[release] zip it and ship (e.g. Compress-Archive).")


if __name__ == "__main__":
    main()
