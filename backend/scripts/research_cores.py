# -*- coding: utf-8 -*-
"""Core-asset research: rank pooled funds as potential strategy COREs.

Metrics per fund (research_prices, public db):
  - full-period (2021-09 ~ now) ann return / vol / sharpe / max drawdown
  - 2025+ sub-period ann return / sharpe (user's "25-26 oil supercycle" window)
  - monthly win-rate
  - correlation with gold basket & bond basket
Buckets by name heuristics so we can present "oil / overseas / dividend /
industry / commodity / bond" candidates instead of 7714 raw rows.
"""
import sqlite3
import sys
import math
import re
import numpy as np
import pandas as pd

DB = r"E:\TT_FinKit\backend\finkit_public.db"
FULL_START = "2021-09-01"
SUB_START = "2025-01-01"

sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect(DB, timeout=30)
assets = pd.read_sql(
    "SELECT id, symbol, name, fund_kind, asset_class, region FROM research_assets WHERE status='pooled'",
    conn)
prices = pd.read_sql(
    "SELECT p.asset_id, p.date, p.close FROM research_prices p "
    "JOIN research_assets a ON a.id=p.asset_id WHERE a.status='pooled' AND p.date>='2021-06-01'",
    conn)
conn.close()

px = prices.pivot_table(index="date", columns="asset_id", values="close").sort_index()
px = px.dropna(how="all")
rets = px.pct_change()

# reference series: gold basket proxy = any fund whose name contains 黄金, averaged
gold_ids = assets.loc[assets["name"].str.contains("黄金", na=False), "id"]
bond_ids = assets.loc[assets["name"].str.contains("国开债|纯债|国债", na=False), "id"]
gold_series = px[gold_ids.tolist()].mean(axis=1) if len(gold_ids) else None
bond_series = px[bond_ids.tolist()].mean(axis=1) if len(bond_ids) else None


def metrics(sym_id: str, sub_start: str = SUB_START):
    s = px[sym_id].dropna()
    s.index = pd.to_datetime(s.index)
    if len(s) < 300:
        return None
    r = s.pct_change().dropna()
    years = (pd.Timestamp(s.index[-1]) - pd.Timestamp(s.index[0])).days / 365.25
    ann = (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1
    vol = r.std() * math.sqrt(252)
    sharpe = (r.mean() * 252 - 0.02) / vol if vol > 1e-9 else np.nan
    dd = (s / s.cummax() - 1).min()
    m = s[s.index >= sub_start]
    if len(m) < 120:
        return None
    mr = m.pct_change().dropna()
    myears = (pd.Timestamp(m.index[-1]) - pd.Timestamp(m.index[0])).days / 365.25
    mann = (m.iloc[-1] / m.iloc[0]) ** (1 / myears) - 1
    mvol = mr.std() * math.sqrt(252)
    msharpe = (mr.mean() * 252 - 0.02) / mvol if mvol > 1e-9 else np.nan
    monthly = s.resample("ME").last().pct_change().dropna()
    win = float((monthly > 0).mean())
    corr_g = float(r.corr(gold_series.pct_change().reindex(r.index).dropna())) if gold_series is not None else np.nan
    corr_b = float(r.corr(bond_series.pct_change().reindex(r.index).dropna())) if bond_series is not None else np.nan
    return dict(ann=ann, vol=vol, sharpe=sharpe, mdd=dd,
                sub_ann=mann, sub_sharpe=msharpe, win=win,
                corr_gold=corr_g, corr_bond=corr_b)


BUCKETS = {
    "油气": r"原油|石油|油气|能源化工|石化",
    "海外": r"纳斯达克|纳指|标普|道琼斯|美国|全球|海外|日经|印度|越南|德国",
    "黄金": r"黄金|贵金属|金ETF|上海金",
    "有色/商品": r"有色|铜|豆粕|商品|能源|铁矿|农产品|期货",
    "红利低波": r"红利|低波|高股息|股息",
    "科技成长": r"半导体|芯片|人工智能|云计算|软件|计算机|科技|电子信息|数字经济|机器人",
    "医药": r"医药|医疗|生物|创新药",
    "新能源": r"新能源|光伏|锂电|电池|碳中和",
    "消费": r"消费|食品饮料|白酒|家电",
    "金融地产": r"银行|证券|保险|非银|地产|金融",
    "军工": r"军工|国防",
    "宽基": r"沪深300|中证500|中证800|中证1000|中证A500|创业板|科创|上证50|MSCI|北证|中证全指",
    "短债/利率": r"国开债|同业存单|短债|利率债|国债",
}


def bucket_of(name: str) -> str:
    for b, pat in BUCKETS.items():
        if re.search(pat, name):
            return b
    return "其他"


rows = []
id2row = assets.set_index("id")
for aid in px.columns:
    if aid not in id2row.index:
        continue
    m = metrics(aid)
    if not m:
        continue
    info = id2row.loc[aid]
    rows.append(dict(symbol=info["symbol"], name=info["name"], bucket=bucket_of(info["name"]), **m))

df = pd.DataFrame(rows)
df = df.sort_values("sub_sharpe", ascending=False)
df.to_csv(r"E:\TT_FinKit\backend\core_research_full.csv", index=False, encoding="utf-8-sig")

print(f"total funds evaluated: {len(df)}\n")
print("=" * 100)
print("TOP 40 by 2025+ sharpe (candidates for CORE, min 300d history):")
cols = ["symbol", "name", "bucket", "ann", "vol", "sharpe", "mdd", "sub_ann", "sub_sharpe", "win", "corr_gold", "corr_bond"]
head = df.head(40)[cols].copy()
for c in ("ann", "vol", "sub_ann"):
    head[c] = (head[c] * 100).round(1)
for c in ("sharpe", "sub_sharpe", "win", "corr_gold", "corr_bond"):
    head[c] = head[c].round(2)
head["mdd"] = (head["mdd"] * 100).round(1)
print(head.to_string(index=False))

print("\n" + "=" * 100)
print("PER-BUCKET champions (best 2025+ sharpe, min ann>10%):")
for b in BUCKETS:
    sub = df[(df.bucket == b) & (df.ann > 0.10)].head(3)
    if not len(sub):
        continue
    print(f"\n-- {b} --")
    out = sub[cols].copy()
    for c in ("ann", "vol", "sub_ann"):
        out[c] = (out[c] * 100).round(1)
    for c in ("sharpe", "sub_sharpe", "win", "corr_gold", "corr_bond"):
        out[c] = out[c].round(2)
    out["mdd"] = (out["mdd"] * 100).round(1)
    print(out.to_string(index=False))
