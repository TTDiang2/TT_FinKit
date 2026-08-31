"""RSS 事件驱动原型（用户拍板 2026-08-29：先建采集原型 + 只读展示，因子映射后置）。

数据流：公开 RSS 源（Google News 关键词检索 + 可扩展）→ rss_events 表（按 link 去重）
→ /api/monitor/events → 监控页「驱动事件」tab。

资产映射：先用轻量关键词表（events ASSET_KEYWORDS）做 hint 标注，
信号密度/质量观察 2~4 周后再决定是否升级为正式因子。

不引入新依赖：标准库 urllib + xml.etree 解析 RSS 2.0 / Atom。
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "finkit.db"

FEEDS: list[dict] = [
    {"name": "GoogleNews-美联储", "url": "https://news.google.com/rss/search?q=%E7%BE%8E%E8%81%94%E5%82%A8&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
    {"name": "GoogleNews-降息", "url": "https://news.google.com/rss/search?q=%E9%99%8D%E6%81%AF&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
    {"name": "GoogleNews-黄金", "url": "https://news.google.com/rss/search?q=%E9%BB%84%E9%87%91&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
    {"name": "GoogleNews-半导体", "url": "https://news.google.com/rss/search?q=%E5%8D%8A%E5%AF%BC%E4%BD%93&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
    {"name": "GoogleNews-A股", "url": "https://news.google.com/rss/search?q=A%E8%82%A1&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"},
]

# 关键词 → 资产类别提示（轻量映射，原型阶段）
ASSET_KEYWORDS: list[tuple[str, str, str]] = [
    (r"美联储|FOMC|议息|降息|加息", "rates", "rates"),
    (r"黄金|金价|COMEX", "gold", "bullish_or_neutral"),
    (r"半导体|芯片|晶圆", "semis", None),
    (r"原油|OPEC|油价", "oil", None),
    (r"A股|沪深|上证|创业板", "a_share", None),
    (r"国债|债券|利率", "bond", None),
]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS rss_events (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    link TEXT,
    published TEXT,
    fetched_at TEXT,
    keyword TEXT,
    asset_class TEXT,
    sentiment TEXT
)
"""


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FinKit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def parse_feed(xml_bytes: bytes) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    # RSS 2.0
    for item in root.iter("item"):
        title = _strip(item.findtext("title") or "")
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        if title and link:
            items.append({"title": title, "link": link, "published": pub})
    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{ns}entry"):
        title = _strip(entry.findtext(f"{ns}title") or "")
        link_el = entry.find(f"{ns}link")
        link = link_el.get("href") if link_el is not None else ""
        pub = entry.findtext(f"{ns}published") or ""
        if title and link:
            items.append({"title": title, "link": link, "published": pub})
    return items


def classify(title: str) -> tuple[str | None, str | None]:
    for pattern, asset_class, sentiment in ASSET_KEYWORDS:
        if re.search(pattern, title):
            return asset_class, sentiment
    return None, None


def collect(db_path: str = str(DB), throttle_s: float = 1.5) -> dict:
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute(CREATE_SQL)
    conn.commit()
    added, seen = 0, 0
    for feed in FEEDS:
        try:
            body = _fetch(feed["url"])
        except Exception as e:  # noqa: BLE001 — 单源失败不阻断
            print(f"[rss] {feed['name']} fetch failed: {e}", flush=True)
            continue
        now = datetime.utcnow().isoformat()
        for it in parse_feed(body):
            seen += 1
            eid = _hash(it["link"])
            exists = conn.execute("SELECT 1 FROM rss_events WHERE id=?", (eid,)).fetchone()
            if exists:
                continue
            asset_class, sentiment = classify(it["title"])
            conn.execute(
                "INSERT OR IGNORE INTO rss_events (id, source, title, link, published, fetched_at, keyword, asset_class, sentiment)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (eid, feed["name"], it["title"], it["link"], it["published"], now,
                 feed["name"].replace("GoogleNews-", ""), asset_class, sentiment),
            )
            added += 1
        conn.commit()
        time.sleep(throttle_s)
    conn.close()
    return {"feeds": len(FEEDS), "items_seen": seen, "added": added}


def list_events(db_path: str = str(DB), limit: int = 100,
                asset_class: str | None = None) -> list[dict]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(CREATE_SQL)
    if asset_class:
        rows = conn.execute(
            "SELECT * FROM rss_events WHERE asset_class=? ORDER BY fetched_at DESC LIMIT ?",
            (asset_class, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM rss_events ORDER BY fetched_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    r = collect()
    print(f"collect done: {r}")
