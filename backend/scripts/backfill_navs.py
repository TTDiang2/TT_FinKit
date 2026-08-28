"""Backfill NAV history for research assets — eastmoney only, never iFinD.

Module-based selection (user-approved): pick representative funds per module
and materialize each module as a research_group (标的组合):

  index_passive   被动指数代表
  index_enhanced  指数增强代表
  macro_asset     大类资产代表（黄金/原油/商品/境内权益/境内债/境外股市）
  money           货币基金代表
  qdii            QDII 代表
  industry        行业代表
  bond_pure       纯债代表
  strategy        策略型代表

Rules: C-share preferred inside each bucket, smallest symbol tie-break,
one fund per family (normalized name), pooled assets always first.
Resumable (DB state = progress). Conservative throttle: serial, 2-4s jitter,
5-min pause every 50 fetches, nightly pause 23:30-07:30.

Usage (from backend/):
  python scripts/backfill_navs.py --dry-run          # show plan per module
  python scripts/backfill_navs.py --create-groups    # write 8 research groups
  python scripts/backfill_navs.py                    # fetch all modules
  python scripts/backfill_navs.py --modules macro_asset,index_passive --limit 100
"""
from __future__ import annotations

import argparse
import asyncio
import random
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_PATH = Path(__file__).resolve().parents[1] / "finkit.db"
YEARS_BACK = 5
FETCH_MIN_S, FETCH_MAX_S = 2.0, 4.0
PAUSE_EVERY_N = 50
PAUSE_SECONDS = 300
NIGHT_START, NIGHT_END = (23, 30), (7, 30)

MODULE_ORDER = ["index_passive", "index_enhanced", "macro_asset", "money",
                "qdii", "industry", "bond_pure", "strategy"]
MODULE_LABELS = {
    "index_passive": "被动指数代表", "index_enhanced": "指数增强代表",
    "macro_asset": "大类资产代表", "money": "货币基金代表",
    "qdii": "QDII代表", "industry": "行业代表",
    "bond_pure": "纯债代表", "strategy": "策略代表",
}

_INDEX_WHITELIST = [
    "沪深300", "中证500", "中证800", "中证1000", "中证2000", "中证A500", "中证全指",
    "上证50", "上证180", "创业板", "科创50", "科创100", "北证50", "深证100",
    "MSCI中国A", "中证红利", "红利指数", "标普中国A股红利", "央视50", "中证龙头",
    "纳斯达克", "纳指", "标普", "道琼斯", "日经", "恒生指数", "恒生科技", "恒生国企",
    "德国DAX", "法国CAC", "英国富时", "印度", "越南", "巴西", "中东",
]
_ENHANCE_PAT = re.compile(r"增强")
_QDII_PAT = re.compile(r"QDII|全球精选|美国|亚洲|新兴市场|大中华|海外|香港优选")
_GOLD_PAT = re.compile(r"黄金|贵金属|金ETF|上海金")
_OIL_PAT = re.compile(r"原油|石油|油气")
_COMMODITY_PAT = re.compile(r"(?<!品质)商品|有色金属|豆粕|铁矿|农产品|能源化工")
_CN_EQUITY_PAT = re.compile("|".join(_INDEX_WHITELIST[:15]))
_CN_BOND_PAT = re.compile(r"同业存单|政策性金融债|国债|地方政府债|国开债")
_INDUSTRY_KEYS = [
    "医药", "医疗", "生物", "创新药", "食品饮料", "白酒", "消费", "家电",
    "半导体", "芯片", "电子", "计算机", "软件", "云计算", "人工智能", "通信",
    "新能源", "光伏", "锂电", "电池", "军工", "国防", "汽车", "智能汽车",
    "机械", "高端装备", "化工", "钢铁", "煤炭", "有色", "房地产", "地产",
    "银行", "证券保险", "非银", "农业", "养殖", "传媒", "游戏", "影视",
    "旅游", "环保", "建材", "电力", "交通运输", "物流", "纺织", "基建",
]
_PURE_BOND_PAT = re.compile(r"纯债")
_STRATEGY_PAT = re.compile(r"量化|对冲|绝对收益|多因子|Alpha|轮动|趋势|FOF|平衡混合|目标日期|养老")
_MONEY_PAT = re.compile(r"货币|现金宝|添利|日利|增利|快线|钱包|理财债")
_MM_FUND_NAMES = ["余额宝", "华宝添益", "银华日利", "建信现金添利", "鹏华增值宝",
                  "招商招钱宝", "南方天天利", "广发天天红"]

_SHARE_SUFFIX = re.compile(r"[（(]?(人民币|美元现汇|港元|发起式|联接基金?|ETF|LOF)[）)]?$")
_CLASS_TOKEN = re.compile(r"[（(]?\s*([ABCEIHO])\s*[类]?[）)]?$")


def normalize_family_name(name: str) -> str:
    s = (name or "").strip().upper()
    s = re.sub(r"\s+", "", s)
    for _ in range(3):
        s2 = _CLASS_TOKEN.sub("", s)
        s2 = _SHARE_SUFFIX.sub("", s2)
        if s2 == s:
            break
        s = s2
    return s


def is_c_share(name: str) -> bool:
    return bool(re.search(r"C[）)]?$", (name or "").strip().upper()))


def bad_for_rep(c: dict) -> bool:
    """硬违规不当代表：非开放申购 / 日限额<1000（与入池审查同口径）。"""
    status = (c.get("purchase_status") or "").strip()
    if status and status != "开放申购":
        return True
    limit = c.get("purchase_limit")
    return limit is not None and limit < 1000


def classify(name: str, fund_kind: str, asset_class: str) -> dict[str, str]:
    n = (name or "").strip()
    k = fund_kind or ""
    acls = asset_class or ""
    out: dict[str, str] = {}
    if _MONEY_PAT.search(n) or "货币" in k or "货币" in acls:
        hit = next((m for m in _MM_FUND_NAMES if m in n), None)
        if hit:
            out["money"] = hit

    is_qdii = "QDII" in n.upper() or "QDII" in k or bool(_QDII_PAT.search(n))
    enhanced = bool(_ENHANCE_PAT.search(n))
    passive_hit = next((ix for ix in _INDEX_WHITELIST if ix in n), None)

    if enhanced and passive_hit:
        out["index_enhanced"] = passive_hit
    elif passive_hit and not enhanced:
        out["index_passive"] = passive_hit

    if _GOLD_PAT.search(n):
        out.setdefault("macro_asset", "黄金")
    elif _OIL_PAT.search(n):
        out.setdefault("macro_asset", "原油油气")
    elif _COMMODITY_PAT.search(n):
        out.setdefault("macro_asset", "大宗商品")
    elif is_qdii and any(w in n for w in ("纳斯达克", "纳指", "标普", "道琼斯", "美国")):
        out.setdefault("macro_asset", "境外股市")
    elif passive_hit and not enhanced and any(w in n for w in ("联接", "ETF")) and "纳斯达克" not in n and "标普" not in n:
        out.setdefault("macro_asset", "境内权益")
    if _CN_BOND_PAT.search(n):
        out.setdefault("macro_asset", "境内债市")

    if is_qdii:
        sub = ("美股" if any(w in n for w in ("纳斯达克", "纳指", "标普", "道琼斯", "美国"))
               else "港股" if any(w in n for w in ("恒生", "香港", "大中华"))
               else "商品" if _GOLD_PAT.search(n) or _OIL_PAT.search(n)
               else "日经" if "日经" in n
               else "印度" if "印度" in n
               else "越南" if "越南" in n
               else "欧洲" if any(w in n for w in ("德国", "法国", "欧洲", "DAX"))
               else "全球")
        out["qdii"] = sub

    ind = next((i for i in _INDUSTRY_KEYS if i in n), None)
    if ind:
        out["industry"] = ind
    if _PURE_BOND_PAT.search(n):
        out["bond_pure"] = n[:4]          # 每家公司/系列取 1 只代表
    if _STRATEGY_PAT.search(n):
        out["strategy"] = next(
            (s for s in ("量化", "对冲", "绝对收益", "多因子", "FOF", "养老", "轮动") if s in n), "其他策略")
    return out


def _better(a: dict, b: dict) -> bool:
    """True when a should replace b as bucket/family representative."""
    if bad_for_rep(a) != bad_for_rep(b):
        return not bad_for_rep(a)
    if a["pooled"] != b["pooled"]:
        return a["pooled"]
    ca, cb = is_c_share(a["name"]), is_c_share(b["name"])
    if ca != cb:
        return ca
    return a["symbol"] < b["symbol"]


def build_plan(conn: sqlite3.Connection) -> tuple[dict[str, list[dict]], dict]:
    rows = conn.execute(
        "SELECT id, symbol, exchange, name, status, is_money_market, fund_kind, asset_class, "
        "purchase_status, purchase_limit "
        "FROM research_assets WHERE exchange = 'FUND_CN'"
    ).fetchall()
    latest = dict(conn.execute(
        "SELECT asset_id, MAX(date) FROM research_prices GROUP BY asset_id"
    ).fetchall())
    horizon = (date.today() - timedelta(days=int(YEARS_BACK * 365.25) - 14)).isoformat()

    candidates = []
    for aid, sym, exch, name, status, mm, kind, acls, pstat, plimit in rows:
        if latest.get(aid) and latest[aid] <= horizon:
            continue
        candidates.append({
            "id": aid, "symbol": sym, "exchange": exch or "FUND_CN",
            "name": name or sym, "pooled": status == "pooled",
            "is_mm": bool(mm), "fund_kind": kind or "", "asset_class": acls or "",
            "purchase_status": pstat or "", "purchase_limit": plimit,
            "last": latest.get(aid),
        })

    fam_best: dict[str, dict] = {}
    for c in candidates:
        key = ("MM:" if c["is_mm"] else "F:") + normalize_family_name(c["name"])
        cur = fam_best.get(key)
        if cur is None or _better(c, cur):
            fam_best[key] = c
    reps = list(fam_best.values())

    buckets: dict[tuple[str, str], list[dict]] = {}
    for c in reps:
        for module, sub in classify(c["name"], c["fund_kind"], c["asset_class"]).items():
            buckets.setdefault((module, sub), []).append(c)

    SUB_CAPS = {"macro_asset": 4}     # 大类资产每子类最多 4 只 → 模块 15-20 只
    plan: dict[str, list[dict]] = {m: [] for m in MODULE_ORDER}
    for (module, _sub), members in buckets.items():
        members.sort(key=lambda c: (bad_for_rep(c), not c["pooled"], not is_c_share(c["name"]), c["symbol"]))
        cap = SUB_CAPS.get(module, 1)
        for c in members[:cap]:
            c["module"] = module
            plan[module].append(c)
    for m in plan:
        plan[m].sort(key=lambda r: (not r["pooled"], r["symbol"]))
        if m in MODULE_CAPS and len(plan[m]) > MODULE_CAPS[m]:
            plan[m] = plan[m][:MODULE_CAPS[m]]
    return plan, {"candidates": len(candidates), "families": len(fam_best)}


MODULE_CAPS = {"bond_pure": 15, "industry": 45}   # keep「代表池」几十只量级


def upsert_groups(conn: sqlite3.Connection, plan: dict[str, list[dict]]) -> None:
    user = conn.execute(
        "SELECT user_id FROM research_assets GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if not user:
        raise SystemExit("no research assets / user found")
    uid = user[0]
    for module in MODULE_ORDER:
        name = MODULE_LABELS[module]
        ids = [r["id"] for r in plan[module]]
        row = conn.execute(
            "SELECT id FROM research_groups WHERE user_id=? AND name=?", (uid, name)
        ).fetchone()
        if row:
            gid = row[0]
            conn.execute("DELETE FROM research_group_members WHERE group_id=?", (gid,))
        else:
            gid = f"grp_{module}"
            conn.execute(
                "INSERT INTO research_groups (id, user_id, name, note) VALUES (?,?,?,?)",
                (gid, uid, name, "回填脚本自动生成的模块代表池"),
            )
        conn.executemany(
            "INSERT OR IGNORE INTO research_group_members (group_id, asset_id) VALUES (?, ?)",
            [(gid, aid) for aid in ids],
        )
        print(f"[group] {name}: {len(ids)} members", flush=True)
    conn.commit()


def upsert_prices(conn: sqlite3.Connection, asset_id: str, series: list[dict]) -> int:
    """Returns actually-inserted row count (INSERT OR IGNORE silently skips
    NOT NULL/UNIQUE violations, so len(rows) would lie)."""
    import uuid
    rows = [(str(uuid.uuid4()), asset_id, p["date"], float(p["close"]), "eastmoney")
            for p in series if p.get("date") and p.get("close") is not None]
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO research_prices (id, asset_id, date, close, source) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def wait_if_night() -> None:
    while True:
        now = datetime.now()
        mins = now.hour * 60 + now.minute
        if not (mins >= NIGHT_START[0] * 60 + NIGHT_START[1] or mins < NIGHT_END[0] * 60 + NIGHT_END[1]):
            return
        resume = (datetime(now.year, now.month, now.day, NIGHT_END[0], NIGHT_END[1])
                  if now.hour < 12 else
                  datetime(now.year, now.month, now.day) + timedelta(days=1, hours=NIGHT_END[0], minutes=NIGHT_END[1]))
        print(f"[night-pause] {now:%H:%M} in night window, resume ~{resume:%m-%d %H:%M}", flush=True)
        time.sleep(60)


async def fetch(symbol: str, exchange: str, begin: str, end: str) -> tuple[list[dict], str]:
    from app.services.nav_history import fetch_history_series
    return await fetch_history_series(symbol, exchange, begin, end,
                                      ifind_user=None, ifind_pass=None)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modules", default=",".join(MODULE_ORDER))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--create-groups", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="with --create-groups: only write groups")
    ap.add_argument("--begin", default="")
    args = ap.parse_args()
    wanted = [m for m in args.modules.split(",") if m in MODULE_ORDER]

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    plan, stats = build_plan(conn)

    queue: list[dict] = []
    seen: set[str] = set()
    for m in MODULE_ORDER:
        if m not in wanted:
            continue
        for r in plan[m]:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            queue.append(r)
    print(f"plan: {len(queue)} funds (all-modules total={sum(len(v) for v in plan.values())}, "
          f"candidates={stats['candidates']}, families={stats['families']})", flush=True)

    if args.dry_run:
        for m in wanted:
            print(f"\n== {MODULE_LABELS[m]} ({len(plan[m])}) ==")
            for r in plan[m]:
                print(f"  {r['symbol']} {r['name'][:26]:<26} last={r['last'] or '-'}")
        return

    if args.create_groups:
        upsert_groups(conn, plan)
    if args.no_fetch:
        return

    end = date.today().isoformat()
    done = errors = inserted_total = 0
    since_run = time.time()
    try:
        for i, r in enumerate(queue, 1):
            wait_if_night()
            if args.limit and done >= args.limit:
                print(f"[stop] --limit {args.limit} reached", flush=True)
                break
            default_begin = (date.today() - timedelta(days=int(YEARS_BACK * 365.25))).isoformat()
            begin = args.begin or ((date.fromisoformat(r["last"]) + timedelta(days=1)).isoformat() if r["last"] else default_begin)
            if begin >= end:
                continue
            try:
                series, source = await fetch(r["symbol"], r["exchange"], begin, end)
                n = upsert_prices(conn, r["id"], series)
                inserted_total += n
                done += 1
                print(f"[{i}/{len(queue)}] {r['symbol']} {r['name'][:20]} +{n} rows ({source})", flush=True)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                errors += 1
                print(f"[{i}/{len(queue)}] {r['symbol']} ERROR {type(e).__name__}: {e}", flush=True)
            if done and done % PAUSE_EVERY_N == 0:
                print(f"[pause] {done} fetched, resting {PAUSE_SECONDS}s", flush=True)
                time.sleep(PAUSE_SECONDS)
            time.sleep(random.uniform(FETCH_MIN_S, FETCH_MAX_S))
    except KeyboardInterrupt:
        print("\n[interrupt] safe to stop — re-run resumes from DB state", flush=True)
    mins = (time.time() - since_run) / 60
    print(f"done: fetched={done} inserted={inserted_total} errors={errors} in {mins:.0f} min", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
