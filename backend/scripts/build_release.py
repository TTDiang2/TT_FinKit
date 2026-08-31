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
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DESKTOP = ROOT / "build" / "desktop"
LAUNCHER = ROOT / "launcher"          # 启动器唯一来源，勿再从 build/desktop 拷旧版
RELEASE = ROOT / "release"
# 桌面壳 FinKit.exe 内嵌打开的端口，必须与 launcher/FinKit.pyw 的 PORT 一致
PORT = 8100


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def build_backend_exe(out_dir: Path) -> None:
    """打包后端 exe。

    frontend/dist 必须一起打进去：桌面壳 FinKit.exe 只是个浏览器窗口，
    打开 http://127.0.0.1:8100，页面由后端自己 serve。少了这一步就是
    「127.0.0.1 拒绝连接」或者 "Frontend not built"。

    PyInstaller 输出到独立 staging 目录（而非直接写 out_dir）：它覆盖同名
    旧 exe 时要先删除，大文件删除容易被回收站拒绝（safe-delete/同名冲突），
    staging 每次都是新目录就没有这个问题。打包完再复制进 out_dir。
    """
    entry = BACKEND / "entry_desktop.py"
    if not (FRONTEND_DIST / "index.html").is_file():
        raise SystemExit("frontend/dist/index.html 不存在——先 npm run build")
    staging = ROOT / "build" / "pyinstaller" / "dist"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", "FinKitBackend",
        "--distpath", str(staging),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--specpath", str(ROOT / "build" / "pyinstaller"),
        "--collect-all", "app",
        "--collect-all", "uvicorn",
        "--collect-all", "finkit_strategy",
        "--hidden-import", "aiosqlite",
        "--hidden-import", "PyJWT",
        # Windows 的 --add-data 分隔符是 ';'
        "--add-data", f"{FRONTEND_DIST}{os.pathsep}frontend{os.sep}dist",
        "--noconfirm",
        str(entry),
    ], cwd=str(BACKEND))
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staging / "FinKitBackend.exe", out_dir / "FinKitBackend.exe")


def prepare_dest(dest: Path) -> None:
    """增量清理：只删应用文件，保留 data/finkit_public.db（2.6GB，重拷很慢）。

    不做 rmtree —— release 目录里既有大文件也有对方的个人库，整目录删除
    风险高且没必要。将被 copy2 覆盖的应用文件删除失败时直接忽略
    （覆盖写不需要先删；删不掉通常只是回收站拒绝同名文件）。
    """
    dest.mkdir(parents=True, exist_ok=True)
    for rel in ("FinKit.exe", "FinKit.pyw", "FinKit-Desktop.bat", "README.txt",
                "backend/FinKitBackend.exe", "backend/finkit.db",
                "backend/backend.log"):
        p = dest / rel
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass  # copy2 会覆盖之
    # 误启动时产生的临时 sqlite 伴生文件
    for p in (dest / "data").glob("finkit_private.db-*"):
        try:
            p.unlink()
        except OSError:
            pass


def assemble(version: str, skip_backend_build: bool = False) -> Path:
    dest = RELEASE / f"FinKit-v{version}"
    prepare_dest(dest)

    backend_out = dest / "backend"
    backend_out.mkdir(exist_ok=True)
    if skip_backend_build:
        prev = RELEASE / "FinKitBackend.exe"
        if not prev.exists():
            raise SystemExit("--skip-backend-build: 找不到 release/FinKitBackend.exe（先手动打包一次）")
        shutil.copy2(prev, backend_out / "FinKitBackend.exe")
    else:
        build_backend_exe(backend_out)

    # frontend shell + launcher（启动器只从 launcher/ 取，build/desktop 下的是旧版）
    shutil.copy2(DESKTOP / "FinKit.exe", dest / "FinKit.exe")
    for name in ("FinKit-Desktop.bat", "FinKit.pyw"):
        src = LAUNCHER / name
        if not src.exists():
            raise SystemExit(f"缺 launcher/{name}")
        shutil.copy2(src, dest / name)

    # public db 模板（已存在且未加 --refresh-data 就复用，省一次 2.6GB 拷贝）
    pub_src = BACKEND / "finkit_public.db"
    if not pub_src.exists():
        raise SystemExit("缺 finkit_public.db——先跑 scripts/migrate_to_split_db.py 生成")
    data = dest / "data"
    data.mkdir(exist_ok=True)
    pub_dst = data / "finkit_public.db"
    if REFRESH_DATA or not pub_dst.exists():
        print(f"[release] 复制 public db（{pub_src.stat().st_size / 1e6:.0f} MB）…", flush=True)
        shutil.copy2(pub_src, pub_dst)
    else:
        print("[release] 复用已有 data/finkit_public.db（加 --refresh-data 可强制更新）", flush=True)

    # 发行包绝不能带 private 库（本机测试/开发时可能已被后端生成过）
    for junk in ("finkit_private.db", "finkit_private.db-shm", "finkit_private.db-wal",
                 "finkit_public.db-shm", "finkit_public.db-wal", "backend.log"):
        p = data / junk
        if p.exists():
            p.unlink()
            print(f"[release] 清理发行包内的 {junk}", flush=True)

    readme = dest / "README.txt"
    readme.write_text(
        "FinKit — 首次使用\n"
        "================\n"
        "1. 双击 FinKit-Desktop.bat（或 FinKit.pyw）。\n"
        "2. 首次启动自动创建空白数据库 data/finkit_private.db，注册你的账号即可。\n"
        "3. data/finkit_public.db 内置标的池/因子/策略骨架，请勿手改。\n\n"
        "你的个人数据（交易/持仓/回测）只存在于本机 data/finkit_private.db，\n"
        "不会随任何更新包外发。\n\n"
        f"服务端口：127.0.0.1:{PORT}（桌面壳已内置该地址，不要手改）。\n"
        "启动异常时看同目录 backend.log 的末尾几行。\n",
        encoding="utf-8",
    )
    return dest


# 由 main() 赋值：--refresh-data 时强制重拷 public db
REFRESH_DATA = False


def main() -> None:
    global REFRESH_DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--skip-backend-build", action="store_true",
                    help="复用已打包的 FinKitBackend.exe")
    ap.add_argument("--refresh-data", action="store_true",
                    help="强制重拷 data/finkit_public.db（默认复用）")
    args = ap.parse_args()
    REFRESH_DATA = args.refresh_data

    if not FRONTEND_DIST.is_dir():
        raise SystemExit("frontend/dist 不存在——先 npm run build")
    if not (DESKTOP / "FinKit.exe").exists():
        raise SystemExit("build/desktop/FinKit.exe 不存在——先跑 Pake 打包")

    dest = assemble(args.version, skip_backend_build=args.skip_backend_build)
    print(f"\n[release] assembled: {dest}")
    print("[release] zip it and ship (e.g. Compress-Archive).")


if __name__ == "__main__":
    main()
