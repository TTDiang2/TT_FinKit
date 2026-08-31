# -*- coding: utf-8 -*-
"""发行包 public 库的"认领"逻辑。

背景：发行时 public 库里的标的/组合/因子数据带着原作者的 user_id，
而路由一律按"当前登录用户"过滤——收件人注册的新账号会看到空列表。

做法：后端启动时（以及首个用户注册后），把 public 库里 user_id 不属于
本机任何用户的行，统一改挂到本机主用户（最早注册者）名下。
- 行 id 不变 => research_prices / factor_values / group_members 等按 id 关联的数据全部保持有效
- 发行包的 public db 是本机模板文件，本地改写无副作用、不会回传
- 开发环境作者本人即主用户 => 天然 no-op
- 多用户安装只认领给主用户（桌面应用单用户是常态，多用户时打日志提示）
"""
import logging
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote

from ..config import _resolve_private_url, _resolve_public_url, is_split_mode

log = logging.getLogger("finkit.db_adopt")

_SQLITE_URL_RE = re.compile(r"^sqlite(?:\+aiosqlite)?:///(.+)$")

# (table, 冲突列)。唯一约束冲突时：本机用户自建的行让位给发行内容（后者更全）。
_ADOPT_TABLES: list[tuple[str, list[str]]] = [
    ("research_assets", ["symbol"]),
    ("research_groups", ["name"]),
    ("factor_evaluations", ["factor_key"]),
    ("factor_ic_points", ["factor_key", "date"]),
]


def _sqlite_path(url: str | None) -> Path | None:
    if not url:
        return None
    m = _SQLITE_URL_RE.match(url)
    if not m:
        return None  # 非 sqlite（如 postgres）不做认领
    return Path(unquote(m.group(1)))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row is not None


def adopt_public_assets(
    pub_path: str | Path | None = None, prv_path: str | Path | None = None
) -> dict:
    """把 public 库中的用户数据认领给本机主用户。返回执行摘要。"""
    if pub_path is None or prv_path is None:
        if not is_split_mode():
            return {"skipped": "single-db mode"}
        pub_path = _sqlite_path(_resolve_public_url())
        prv_path = _sqlite_path(_resolve_private_url())
        if not pub_path or not prv_path:
            return {"skipped": "non-sqlite urls"}
    pub_path, prv_path = Path(pub_path), Path(prv_path)
    if not pub_path.exists():
        return {"skipped": f"public db missing: {pub_path}"}
    if not prv_path.exists():
        return {"skipped": f"private db missing (尚未注册任何用户): {prv_path}"}

    pub = sqlite3.connect(str(pub_path))
    prv = sqlite3.connect(str(prv_path))
    try:
        users = [r[0] for r in prv.execute(
            "select id from users order by created_at asc, rowid asc").fetchall()]
        if not users:
            return {"skipped": "no users yet"}
        target = users[0]
        known = set(users)

        changed: dict[str, int] = {}
        for table, cols in _ADOPT_TABLES:
            if not _table_exists(pub, table):
                continue
            stray = [r[0] for r in pub.execute(
                f"select distinct user_id from {table}").fetchall()
                if r[0] not in known]
            if not stray:
                continue

            # 1. 先清掉主用户与发行内容冲突的自建行（发行内容优先）
            coll_cond = " and ".join(f"s2.{c} = {table}.{c}" for c in cols)
            placeholders = ",".join("?" for _ in stray)
            cur = pub.execute(
                f"delete from {table} where user_id = ? and exists ("
                f"  select 1 from {table} s2 where s2.user_id in ({placeholders})"
                f"  and {coll_cond})",
                [target, *stray])
            removed = cur.rowcount

            # 2. 发行数据改挂主用户
            cur = pub.execute(
                f"update {table} set user_id = ? where user_id in ({placeholders})",
                [target, *stray])
            changed[table] = cur.rowcount
            if removed:
                log.info("adopt %s: removed %d colliding local rows", table, removed)

        # 认领后清理可能因组合重名删除而产生的孤儿成员
        if _table_exists(pub, "research_group_members") and changed.get("research_groups"):
            pub.execute(
                "delete from research_group_members "
                "where group_id not in (select id from research_groups)")

        pub.commit()
        if changed:
            log.info("[adopt] public 库数据已认领给主用户 %s: %s", target, changed)
        return {"adopted_to": target, "changed": changed}
    finally:
        pub.close()
        prv.close()
