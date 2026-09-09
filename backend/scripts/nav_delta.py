"""public 库增量同步：导出增量包 / 导入增量包 / 经 GitHub Release 推拉。

解决的场景：public 库（标的 + 净值，2.6GB）太大，没法整库上网盘；
而各台机器各自全量重拉又要 1.3GB 下行 + 7 分钟（pingzhongdata 不论时间范围
都返回全量 JS，流量与更新频率无关）。所以只同步"最近 N 天变化过的行"：

    闲置机：更新净值 → push  → GitHub Release（私有库，单包 ~8MB）
    其他机：          → pull → 秒级 UPSERT 入库

设计要点
- **零第三方依赖**（只用 sqlite3 / zipfile / json / urllib），随便哪个 python 都能跑；
  其他机器上大概率没装项目依赖，这一点是硬要求。
- **幂等**：导入用 ON CONFLICT DO UPDATE，重复导入同一个包不会出错也不会翻倍。
- **无状态**：导出按"日期窗口"取行，不依赖水位文件，因此水位丢失也不会丢数据。
  窗口默认 14 天，既能覆盖日增，也能覆盖源端对最近若干天的回溯修正
  （更新脚本会重拉每只标的的最后一天，修正落在窗口内）。
- 顺带同步 research_assets 全量，避免对端缺标的导致价格行变孤儿。
- 导入后重算派生表 research_asset_stats（标的页「最新数据」读它；它不在包里）。
  这一步 best-effort：拿不到项目模块时只告警不失败，导出/推送路径完全不碰它。
- Release 用**滚动 tag** + 保留最近 N 个 asset，仓库体积恒定，不会累积历史。

用法
    # 闲置机（推）
    python scripts/nav_delta.py export                     # 只导出，默认 14 天窗口
    python scripts/nav_delta.py push                       # 导出 + 推 Release
    python scripts/nav_delta.py push --file 已存在的包.zip  # 只推现成的包

    # 其他机（拉）
    python scripts/nav_delta.py pull                       # 拉最新包 + 直接入库
    python scripts/nav_delta.py pull --dry-run             # 只看不写

    # 手工传包时
    python scripts/nav_delta.py import --file nav_delta_20260908.zip
    python scripts/nav_delta.py import --file xxx.zip --dry-run

GitHub 凭据按此顺序取（都无需交互）：
    FINKIT_GH_TOKEN / GITHUB_TOKEN / GH_TOKEN 环境变量
    → gh auth token
    → git credential fill（复用本机已存的 github.com 凭据，与 git push 同源）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_DIR / "finkit_public.db"
DEFAULT_OUT = BACKEND_DIR.parent / "nav_sync_out"

# --- GitHub Release 通道（私有数据仓库，与 db_release_push.ps1 同一个） ---
DEFAULT_REPO = "TTDiang2/TT_FinKit_Data"
DEFAULT_TAG = "nav-delta"
GH_API = "https://api.github.com"
GH_UPLOAD = "https://uploads.github.com"

# 需要一起同步的表：价格走日期窗口，标的走全量（行数小、且必须保证不缺标的）
PRICE_TABLE = "research_prices"
PRICE_CONFLICT = ["asset_id", "date"]
ASSET_TABLE = "research_assets"
ASSET_CONFLICT = ["id"]


def log(msg: str) -> None:
    print(msg, flush=True)


def resolve_db(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path)
    env = os.environ.get("FINKIT_PUBLIC_DB")
    if env:
        return Path(env)
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from app.config import public_db_path  # noqa: PLC0415

        p = Path(public_db_path())
        if p.exists() and p.stat().st_size > 0:
            return p
    except Exception:
        pass
    for cand in (DEFAULT_DB, BACKEND_DIR / "finkit.db"):
        if cand.exists() and cand.stat().st_size > 0:
            return cand
    return DEFAULT_DB


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def create_table_like(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> None:
    row = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        raise SystemExit(f"源库缺少表 {table}")
    dst.execute(row[0])


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def cmd_export(args) -> int:
    pkg = export_package(args)
    log(f"[next] 其他机器跑：python scripts/nav_delta.py import --file {pkg.name}")
    return 0


def export_package(args) -> Path:
    """导出增量包，返回产物路径（.zip 或 .db）。供 export / push 共用。"""
    db_path = resolve_db(args.db)
    if not db_path.exists() or db_path.stat().st_size == 0:
        log(f"[fatal] 源库不存在或为空：{db_path}")
        return 2

    cutoff = (date.today() - timedelta(days=args.days)).isoformat()
    log(f"[db] {db_path}")
    log(f"[window] {PRICE_TABLE}.date >= {cutoff}（--days {args.days}）")

    src = sqlite3.connect(str(db_path), timeout=60)
    src.execute("PRAGMA journal_mode=WAL")
    src.execute("PRAGMA busy_timeout=30000")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    delta_db = out_dir / f"nav_delta_{stamp}.db"
    if delta_db.exists():
        delta_db.unlink()

    dst = sqlite3.connect(str(delta_db))
    counts: dict[str, int] = {}

    for table in (PRICE_TABLE, ASSET_TABLE):
        create_table_like(src, dst, table)
        cols = table_columns(src, table)
        collist = ", ".join(cols)
        if table == PRICE_TABLE:
            sql = f"SELECT {collist} FROM {table} WHERE date >= ?"
            params: tuple = (cutoff,)
        else:
            sql = f"SELECT {collist} FROM {table}"
            params = ()
        rows = src.execute(sql, params).fetchall()
        placeholders = ", ".join("?" * len(cols))
        dst.executemany(
            f"INSERT INTO {table} ({collist}) VALUES ({placeholders})", rows
        )
        dst.commit()
        counts[table] = len(rows)
        log(f"  {table}: {len(rows)} 行")

    # 日期覆盖情况（供对端核对）
    rng = src.execute(
        f"SELECT MIN(date), MAX(date) FROM {PRICE_TABLE} WHERE date >= ?", (cutoff,)
    ).fetchone()
    latest = src.execute(f"SELECT MAX(date) FROM {PRICE_TABLE}").fetchone()[0]
    src.close()

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "source_db": db_path.name,
        "days_window": args.days,
        "date_from": rng[0],
        "date_to": rng[1],
        "src_latest_date": latest,
        "rows": counts,
        "schema_version": 1,
    }
    dst.execute(
        "CREATE TABLE IF NOT EXISTS _nav_delta_meta (k TEXT PRIMARY KEY, v TEXT)"
    )
    dst.execute(
        "INSERT OR REPLACE INTO _nav_delta_meta (k, v) VALUES ('manifest', ?)",
        (json.dumps(manifest, ensure_ascii=False),),
    )
    dst.commit()
    dst.close()

    mpath = out_dir / f"nav_delta_{stamp}.manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    raw_mb = delta_db.stat().st_size / 1e6
    log(f"[delta] {delta_db.name}  {raw_mb:.1f} MB（未压缩）")

    if args.zip:
        zip_path = out_dir / f"nav_delta_{stamp}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            z.write(delta_db, delta_db.name)
            z.write(mpath, mpath.name)
        delta_db.unlink()
        mpath.unlink()
        zip_mb = zip_path.stat().st_size / 1e6
        log(f"[zip] {zip_path}  {zip_mb:.2f} MB（压缩比 {raw_mb / max(zip_mb, 0.01):.1f}x）")
        return zip_path
    return delta_db


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #
def resolve_package(f: str, out_dir: Path) -> Path:
    """接受 zip / 裸 .db / 目录里的文件名，返回可用的 .db 路径。"""
    p = Path(f)
    if not p.exists():
        cand = out_dir / f
        if cand.exists():
            p = cand
        else:
            raise SystemExit(f"找不到增量包：{f}（也未在 {out_dir} 下找到）")
    if p.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="navdelta_"))
        with zipfile.ZipFile(p) as z:
            z.extractall(tmp)
        dbs = list(tmp.glob("*.db"))
        if not dbs:
            raise SystemExit(f"zip 里没有 .db：{p}")
        log(f"[unzip] {p.name} -> {dbs[0].name}")
        return dbs[0]
    return p


def build_upsert(table: str, cols: list[str], conflict: list[str]) -> str:
    collist = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in conflict)
    return (
        f"INSERT INTO main.{table} ({collist}) "
        f"SELECT {collist} FROM delta.{table} "
        f"WHERE 1=1 "
        f"ON CONFLICT({', '.join(conflict)}) DO UPDATE SET {updates}"
    )


def refresh_stats_table(db_path: Path) -> None:
    """Recompute research_asset_stats after raw prices land in the local DB.

    The delta package carries only research_prices/research_assets; the
    per-asset window table is derived and would otherwise stay frozen at the
    push machine's last run (标的页「最新数据」读的就是它的 last_date）。
    asset_stats imports stdlib only, and the import stays lazy so the
    zero-dependency export/push path is untouched.
    """
    try:
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))
        from app.services.asset_stats import refresh_stats  # noqa: PLC0415

        t0 = time.time()
        rows = refresh_stats(str(db_path))
        log(f"[stats] research_asset_stats 已重算：{rows} 行（{time.time() - t0:.0f}s）")
    except Exception as e:
        log(f"[warn] 派生表 research_asset_stats 重算失败：{type(e).__name__}: {e}")
        log("        可手动补跑：python scripts/refresh_asset_stats.py")


def cmd_import(args) -> int:
    db_path = resolve_db(args.db)
    if not db_path.exists() or db_path.stat().st_size == 0:
        log(f"[fatal] 目标库不存在或为空：{db_path}")
        log("        新机器请先从闲置机拷贝一份完整 finkit_public.db，再导入增量。")
        return 2

    out_dir = Path(getattr(args, "out", None) or DEFAULT_OUT)
    delta_db = resolve_package(args.file, out_dir)
    log(f"[db] {db_path}")
    log(f"[pkg] {delta_db}")

    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    dmeta = sqlite3.connect(str(delta_db))
    try:
        mrow = dmeta.execute(
            "SELECT v FROM _nav_delta_meta WHERE k='manifest'"
        ).fetchone()
        if mrow:
            man = json.loads(mrow[0])
            log(f"[pkg] 生成于 {man.get('generated_at')} | "
                f"日期 {man.get('date_from')} ~ {man.get('date_to')} | "
                f"行数 {man.get('rows')}")
    except sqlite3.Error:
        pass
    dmeta.close()

    if args.dry_run:
        conn.close()
        log("[dry-run] 未做任何写入")
        return 0

    before = conn.total_changes
    conn.execute("ATTACH DATABASE ? AS delta", (str(delta_db),))
    try:
        # 先标的表，保证价格行不会因缺标的而变孤儿
        for table, conflict in ((ASSET_TABLE, ASSET_CONFLICT),
                                (PRICE_TABLE, PRICE_CONFLICT)):
            cols = table_columns(conn, table)
            sql = build_upsert(table, cols, conflict)
            cur = conn.execute(sql)
            log(f"  {table}: 影响 {cur.rowcount} 行")

        orphans = conn.execute(
            "SELECT COUNT(*) FROM delta.research_prices p "
            "WHERE NOT EXISTS (SELECT 1 FROM main.research_assets a WHERE a.id = p.asset_id)"
        ).fetchone()[0]
        if orphans:
            log(f"  [warn] {orphans} 行价格在对端找不到对应标的，已跳过"
                f"（对端 public 库过旧时会出现）")
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE delta")
    conn.commit()

    changed = conn.total_changes - before
    latest = conn.execute(f"SELECT MAX(date) FROM {PRICE_TABLE}").fetchone()[0]
    total = conn.execute(f"SELECT COUNT(*) FROM {PRICE_TABLE}").fetchone()[0]
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    log(f"[done] 写入/更新 {changed} 行 | 库中最新净值日 {latest} | 总行数 {total}")
    if not getattr(args, "no_refresh_stats", False):
        refresh_stats_table(db_path)
    return 0


# --------------------------------------------------------------------------- #
# GitHub Release 通道（零依赖，只用 urllib）
# --------------------------------------------------------------------------- #
def gh_token() -> str:
    for env in ("FINKIT_GH_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        v = os.environ.get(env, "").strip()
        if v:
            log("[auth] 使用环境变量中的 token")
            return v
    for exe in ("gh", r"C:\Program Files\GitHub CLI\gh.exe"):
        try:
            r = subprocess.run([exe, "auth", "token"], capture_output=True,
                               text=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                log(f"[auth] 使用 {exe} 的登录态")
                return r.stdout.strip()
        except Exception:
            continue
    try:
        r = subprocess.run(["git", "credential", "fill"],
                           input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, timeout=30)
        for line in r.stdout.splitlines():
            if line.startswith("password=") and line[9:].strip():
                log("[auth] 使用 git credential store 中的 github.com 凭据")
                return line[9:].strip()
    except Exception:
        pass
    raise SystemExit(
        "[fatal] 拿不到 GitHub 凭据。任选其一：\n"
        "        set GITHUB_TOKEN=ghp_xxx\n"
        "        gh auth login\n"
        "        git 已能免密 push github.com（走 credential store）"
    )


def gh_request(url: str, token: str, method: str = "GET", data: bytes | None = None,
               content_type: str = "application/json", accept: str | None = None,
               timeout: int = 300):
    hdr = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "finkit-nav-delta",
        "Accept": accept or "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if data is not None:
        hdr["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"[fatal] GitHub API {method} {url}\n"
                         f"        HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"[fatal] 网络错误 {method} {url}: {e}") from None
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype and raw[:1] in (b"{", b"["):
        return json.loads(raw.decode("utf-8"))
    return raw


def download_asset(url: str, token: str, dest: Path, expect_size: int = 0,
                   timeout: int = 60, retries: int = 8) -> int:
    """分块下载 Release 资产，支持断点续传与自动重试。

    timeout 是**每次 socket 读**的超时（不是总时长）。GitHub 的资产 CDN 在部分
    网络下只有十几 KB/s，一次性 read() 会被判超时，所以这里按 64KB 分块读，
    卡住就带 Range 头从已下载处续传。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        have = dest.stat().st_size if dest.exists() else 0
        if expect_size and have == expect_size:
            return have
        if have and have >= expect_size > 0:
            dest.unlink()
            have = 0
        hdr = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "finkit-nav-delta",
            "Accept": "application/octet-stream",
        }
        if have:
            hdr["Range"] = f"bytes={have}-"
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200 and have:
                    have = 0  # 服务端不支持 Range，从头再来
                length = resp.headers.get("Content-Length")
                total = (int(length) + have) if length else expect_size or 0
                next_mark = have + 2_000_000
                with open(dest, "ab" if have else "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        if have >= next_mark:
                            next_mark = have + 2_000_000
                            pct = f"{have / total * 100:.0f}%" if total else "?"
                            log(f"      ... {have / 1e6:.1f} MB"
                                + (f" / {total / 1e6:.1f} MB ({pct})" if total else ""))
            if not total or have >= total:
                return have
            log(f"      [warn] 只拿到 {have}/{total} 字节，续传重试（第 {attempt} 次）")
        except Exception as e:  # 网络抖动 / 读超时 / 连接重置
            log(f"      [warn] 中断于 {have / 1e6:.1f} MB：{type(e).__name__} "
                f"{str(e)[:60]}（第 {attempt}/{retries} 次，2 秒后续传）")
            time.sleep(min(2 * attempt, 15))
    raise SystemExit(
        f"[fatal] 下载失败，已重试 {retries} 次。当前进度 {dest.stat().st_size if dest.exists() else 0} 字节。\n"
        f"        网络太差时可用 --timeout 120 放宽读超时后重跑（会自动续传）。"
    )


def gh_release(token: str, repo: str, tag: str, create: bool = True):
    url = f"{GH_API}/repos/{repo}/releases/tags/{tag}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "finkit-nav-delta",
        "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code != 404 or not create:
            raise
    body = json.dumps({
        "tag_name": tag,
        "name": "NAV delta packages (rolling)",
        "body": ("public 库净值增量包，由 nav_delta.py push 自动维护。"
                 "其他机器用 `nav_delta.py pull` 拉取入库。"),
        "prerelease": True,
    }).encode("utf-8")
    return gh_request(f"{GH_API}/repos/{repo}/releases", token,
                      method="POST", data=body)


def cmd_push(args) -> int:
    if args.file:
        pkg = Path(args.file)
        if not pkg.exists():
            cand = Path(args.out) / args.file
            if not cand.exists():
                log(f"[fatal] 找不到包：{args.file}")
                return 2
            pkg = cand
    else:
        pkg = export_package(args)
    size_mb = pkg.stat().st_size / 1e6
    log(f"[pkg] {pkg.name}  {size_mb:.2f} MB")

    token = gh_token()
    rel = gh_release(token, args.repo, args.tag)
    rel_id = rel["id"]
    log(f"[rel] {args.repo} #{rel_id} tag={args.tag}")

    # 同名 asset 必须先删（GitHub 不允许重名覆盖）
    for a in rel.get("assets", []):
        if a["name"] == pkg.name:
            gh_request(f"{GH_API}/repos/{args.repo}/releases/assets/{a['id']}",
                       token, method="DELETE")
            log(f"      removed duplicate {a['name']}")

    with open(pkg, "rb") as f:
        blob = f.read()
    up = gh_request(
        f"{GH_UPLOAD}/repos/{args.repo}/releases/{rel_id}/assets?name={pkg.name}",
        token, method="POST", data=blob, content_type="application/zip")
    log(f"[push] 已上传 {up.get('name')}  {up.get('size', 0) / 1e6:.2f} MB")

    assets = gh_request(
        f"{GH_API}/repos/{args.repo}/releases/{rel_id}/assets?per_page=100", token)
    assets.sort(key=lambda a: a["created_at"], reverse=True)
    for a in assets[args.keep:]:
        gh_request(f"{GH_API}/repos/{args.repo}/releases/assets/{a['id']}",
                   token, method="DELETE")
        log(f"      pruned {a['name']} ({a['size'] / 1e6:.1f} MB, {a['created_at'][:10]})")
    log(f"[done] Release 现保留 {min(len(assets), args.keep)} 个包。"
        f"对端跑：python scripts/nav_delta.py pull")
    return 0


def cmd_pull(args) -> int:
    db_path = resolve_db(args.db)
    if not db_path.exists() or db_path.stat().st_size == 0:
        log(f"[fatal] 目标库不存在或为空：{db_path}")
        log("        新机器请先从闲置机拷一份完整 finkit_public.db，再 pull 增量。")
        return 2

    token = gh_token()
    rel = gh_release(token, args.repo, args.tag, create=False)
    assets = rel.get("assets", [])
    if not assets:
        log(f"[fatal] Release {args.tag} 下还没有任何包。先在闲置机跑 push。")
        return 2
    assets.sort(key=lambda a: a["created_at"], reverse=True)
    if args.date:
        matched = [a for a in assets if args.date in a["name"]]
        if not matched:
            log(f"[fatal] 没有日期戳含 {args.date} 的包。现有：")
            for a in assets[:10]:
                log(f"        {a['name']}  {a['created_at'][:19]}")
            return 2
        asset = matched[0]
    else:
        asset = assets[0]

    log(f"[pkg] {asset['name']}  {asset['size'] / 1e6:.2f} MB  "
        f"推送于 {asset['created_at'][:19]}")

    # 落到固定缓存目录（而非临时目录）：下载中断后重跑可跨次续传
    cache_dir = Path(getattr(args, "out", None) or DEFAULT_OUT) / "_incoming"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="navdelta_pull_"))
    try:
        local = cache_dir / asset["name"]
        got = download_asset(
            f"{GH_API}/repos/{args.repo}/releases/assets/{asset['id']}",
            token, local, expect_size=asset["size"], timeout=args.timeout)
        log(f"[get] 下载完成 {got / 1e6:.2f} MB")

        # 对端已有水位：先报一下，方便判断这次是不是空跑
        conn = sqlite3.connect(str(db_path), timeout=60)
        try:
            latest = conn.execute(
                f"SELECT MAX(date) FROM {PRICE_TABLE}").fetchone()[0]
        finally:
            conn.close()
        log(f"[db] {db_path.name} 当前最新净值日 {latest}")

        args.file = str(local)
        rc = cmd_import(args)
        if rc == 0 and not getattr(args, "dry_run", False):
            local.unlink(missing_ok=True)
            log(f"[clean] 已清除缓存 {local.name}（下次 pull 会重新下载）")
        return rc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="public 库增量同步（导出/导入/推拉）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="导出最近 N 天的增量包")
    ex.add_argument("--db", default="", help="源库路径（默认自动发现）")
    ex.add_argument("--days", type=int, default=14, help="日期窗口，默认 14 天")
    ex.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ex.add_argument("--no-zip", dest="zip", action="store_false", help="不压缩，直接产出 .db")
    ex.set_defaults(zip=True)
    ex.set_defaults(func=cmd_export)

    im = sub.add_parser("import", help="把增量包合并进本地库")
    im.add_argument("--file", required=True, help="增量包（.zip 或 .db，也支持只给文件名）")
    im.add_argument("--db", default="", help="目标库路径（默认自动发现）")
    im.add_argument("--out", default=str(DEFAULT_OUT), help="只给文件名时的查找目录")
    im.add_argument("--dry-run", action="store_true", help="只看元信息，不写入")
    im.add_argument("--no-refresh-stats", action="store_true",
                    help="跳过派生表 research_asset_stats 重算（默认重算，约 2 分钟）")
    im.set_defaults(func=cmd_import)

    pu = sub.add_parser("push", help="导出增量包并推送到 GitHub Release")
    pu.add_argument("--db", default="", help="源库路径（默认自动发现）")
    pu.add_argument("--days", type=int, default=14, help="日期窗口，默认 14 天")
    pu.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    pu.add_argument("--no-zip", dest="zip", action="store_false", help="不压缩")
    pu.add_argument("--file", default="", help="直接推送已存在的包，跳过导出")
    pu.add_argument("--repo", default=DEFAULT_REPO, help=f"数据仓库，默认 {DEFAULT_REPO}")
    pu.add_argument("--tag", default=DEFAULT_TAG, help=f"Release tag，默认 {DEFAULT_TAG}")
    pu.add_argument("--keep", type=int, default=14, help="Release 保留最近几个包，默认 14")
    pu.set_defaults(zip=True)
    pu.set_defaults(func=cmd_push)

    pl = sub.add_parser("pull", help="从 GitHub Release 拉最新包并入库")
    pl.add_argument("--db", default="", help="目标库路径（默认自动发现）")
    pl.add_argument("--repo", default=DEFAULT_REPO, help=f"数据仓库，默认 {DEFAULT_REPO}")
    pl.add_argument("--tag", default=DEFAULT_TAG, help=f"Release tag，默认 {DEFAULT_TAG}")
    pl.add_argument("--date", default="", help="指定日期戳，如 20260908；默认取最新")
    pl.add_argument("--out", default=str(DEFAULT_OUT), help="下载缓存目录")
    pl.add_argument("--dry-run", action="store_true", help="只下载并看元信息，不写入")
    pl.add_argument("--timeout", type=int, default=60,
                    help="每次网络读的超时秒数（非总时长），默认 60；慢网可调到 120")
    pl.add_argument("--no-refresh-stats", action="store_true",
                    help="跳过派生表 research_asset_stats 重算（默认重算，约 2 分钟）")
    pl.set_defaults(func=cmd_pull)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
