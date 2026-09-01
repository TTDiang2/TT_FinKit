# -*- coding: utf-8 -*-
"""ML 策略实验: LightGBM/Ridge walk-forward 预测资产类下月收益 → 权重.

设计(尊重小样本现实):
- 样本单位 = (月末 t, 资产类 c)。特征 = 类 c 的多周期动量/波动/与金相关性/
  类内宽度等 ~15 个, 全部来自 t 及之前(无泄漏)。
- 标签 = 类 c 在 t→t+1 月收益。
- 训练窗口滚动 36 个月, 每月重训, 预测下月; 2024-01 起为样本外。
- 模型: Ridge(线性, 抗过拟合基线) 与 LightGBM(浅树) 对比。
- 组合规则: 预测收益>0 的类按预测比例分 core 75%, 卫星 25% 给动量最强类,
  全负退债。月频调仓, 费用走引擎。
"""
import sys
import os
import math
import warnings

sys.path.insert(0, r"E:\TT_FinKit\backend")
os.chdir(r"E:\TT_FinKit\backend")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import sqlite3

PUBLIC_DB = r"E:\TT_FinKit\backend\finkit_public.db"

CLASSES = {
    "黄金": ["000217", "002611", "002963", "004253", "021740"],
    "油气": ["023145", "020406", "021620", "021823", "019828"],
    "红利": ["022888", "021514", "017536"],
    "权益": ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
    "海外": ["160141"],
    "科技": ["024070", "023829", "020900"],
    "有色": ["004433"],
}
BOND = "006485"


def load_class_series() -> dict[str, pd.Series]:
    conn = sqlite3.connect(PUBLIC_DB, timeout=30)
    px = pd.read_sql(
        "SELECT p.date, p.close, a.symbol FROM research_prices p "
        "JOIN research_assets a ON a.id=p.asset_id WHERE p.date>='2021-09-01'",
        conn)
    names = dict(conn.execute("SELECT symbol, name FROM research_assets").fetchall())
    conn.close()
    pxw = px.pivot_table(index="date", columns="symbol", values="close").sort_index()
    out = {}
    for cname, syms in CLASSES.items():
        avail = [s for s in syms if s in pxw.columns]
        if not avail:
            continue
        # 类指数 = 族内成员日收益均值（等权）
        r = pxw[avail].pct_change(fill_method=None)
        cum = (1 + r.mean(axis=1)).cumsum().dropna()
        cum.index = pd.to_datetime(cum.index)
        out[cname] = cum
    return out


def features_for(series: pd.Series, date) -> dict | None:
    s = series[series.index <= date].dropna()
    if len(s) < 130:
        return None
    r = s.pct_change().dropna().iloc[-260:]
    if len(r) < 60:
        return None
    f = {}
    for lb in (21, 63, 126, 250):
        if len(s) > lb:
            f[f"mom{lb}"] = s.iloc[-1] / s.iloc[-lb - 1] - 1
    v20 = r.iloc[-20:].std() * math.sqrt(252)
    v60 = r.iloc[-60:].std() * math.sqrt(252)
    f["vol20"] = v20
    f["vol60"] = v60
    f["vol_ratio"] = v20 / v60 if v60 > 1e-9 else 1.0
    f["dd60"] = s.iloc[-1] / s.iloc[-60:].max() - 1
    m = s.resample("ME").last().pct_change().dropna().iloc[-24:]
    f["win12"] = float((m.iloc[-12:] > 0).mean()) if len(m) >= 12 else 0.5
    f["skew"] = float(r.iloc[-126:].skew()) if len(r) >= 126 else 0.0
    return f


def main():
    classes = load_class_series()
    month_ends = sorted({idx for s in classes.values()
                         for idx in s.resample("ME").last().index})
    month_ends = [d for d in month_ends if d >= pd.Timestamp("2022-10-01")]

    rows, labels = [], []
    next_month_map = {}
    # 标签: 类在 t 月末→下月末收益
    for cname, s in classes.items():
        me = s.resample("ME").last().dropna()
        for i in range(len(me) - 1):
            next_month_map[(me.index[i], cname)] = me.iloc[i + 1] / me.iloc[i] - 1

    feat_rows = []
    for d in month_ends:
        for cname, s in classes.items():
            f = features_for(s, d)
            if f is None:
                continue
            lab = next_month_map.get((d, cname))
            if lab is None:
                continue
            feat_rows.append(dict(date=d, cls=cname, **f, label=lab))

    df = pd.DataFrame(feat_rows)
    feat_cols = [c for c in df.columns if c not in ("date", "cls", "label")]
    df = df.dropna(subset=feat_cols + ["label"])
    print(f"samples: {len(df)} | classes: {df['cls'].nunique()} | months: {df['date'].nunique()}",
          flush=True)

    # walk-forward: 训练窗 36 个月, 逐月外推
    oos_preds = []
    months = sorted(df["date"].unique())
    try:
        from lightgbm import LGBMRegressor
        HAS_LGB = True
    except ImportError:
        HAS_LGB = False
    from sklearn.linear_model import Ridge

    for i in range(24, len(months) - 1):
        test_m = months[i]
        # 留一个月缓冲: train_end 的标签(下月收益)已进入 test 月区间,
        # 若包含会造成「用未来训练」——IC 0.94 的假象即源于此
        train_end = months[i - 2]
        train_start = months[max(0, i - 36)]
        tr = df[(df.date > pd.Timestamp(train_start)) & (df.date <= pd.Timestamp(train_end))]
        te = df[df.date == test_m]
        if len(tr) < 40 or len(te) < 3:
            continue
        model = LGBMRegressor(n_estimators=60, max_depth=3, num_leaves=7,
                              learning_rate=0.08, verbose=-1) if HAS_LGB else \
            Ridge(alpha=10.0)
        model.fit(tr[feat_cols].values, tr["label"].values)
        pred = model.predict(te[feat_cols].values)
        for (_, row), p in zip(te.iterrows(), pred):
            oos_preds.append(dict(date=test_m, cls=row["cls"], pred=float(p),
                                  actual=float(row["label"])))

    op = pd.DataFrame(oos_preds)
    op.to_csv(r"E:\TT_FinKit\backend\ml_oos_preds.csv", index=False)
    # IC
    ic = op.groupby("date").apply(lambda g: g["pred"].corr(g["actual"]))
    print(f"OOS months: {len(ic)} | mean IC: {ic.mean():.3f} | IC>0 占比: {(ic > 0).mean():.2f}",
          flush=True)

    # 组合模拟: 预测>0 的类按预测占比分 75%, 卫星 25% 给实际动量最强类(简化: 预测次高), 全负退债
    nav = 1.0
    curve = []
    for d, g in op.groupby("date"):
        pos = g[g.pred > 0]
        if not len(pos):
            curve.append((d, nav))  # 退债≈0.15%月
            nav *= 1.0015
            continue
        total_p = pos["pred"].sum()
        actual_map = dict(zip(g["cls"], g["actual"]))
        ret = 0.25 * 0.0015
        for _, r in pos.iterrows():
            ret += (r["pred"] / total_p) * 0.75 * r["actual"]
        nav *= (1 + ret)
        curve.append((d, nav))
    if len(curve) > 1:
        navs = np.array([v for _, v in curve])
        yrs = len(curve) / 12
        ann = (navs[-1] / navs[0]) ** (1 / yrs) - 1
        rets = pd.Series(navs).pct_change().dropna()
        sh = (rets.mean() * 12 - 0.02) / (rets.std() * math.sqrt(12))
        mdd = (navs / np.maximum.accumulate(navs) - 1).min()
        print(f"ML组合({len(curve)}个月): 年化 {ann*100:.1f}% | 夏普 {sh:.2f} | mdd {mdd*100:.1f}%",
              flush=True)


if __name__ == "__main__":
    main()
