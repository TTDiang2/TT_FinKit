"""name: Trinity三明治宏观
description: 恒定核40%(金/油/红利等权) + 卫星60%动量轮动(含科技) + 全池动量转负时卫星减半退债
rebalance_freq: monthly
version: 1
version_note: 1.0-trinity
factor_keys:
---

Trinity 三明治 v1 —— 核（恒定多元）+ 卫星（动量轮动）+ 保护（趋势退避）。

策略逻辑（月频）：
  1. 核 40%：黄金/油气/红利三等权恒持（不动量开关，靠彼此低相关对冲）
  2. 卫星 60%：权益/海外/科技/有色/黄金股类内选强，动量最强前 2 类均分
  3. 保护层：卫星池全部动量转负 → 卫星预算减半退国开债（核不动）
  4. 无 risk_scale（核本身已是分散结构）
"""

from finkit_strategy import Strategy, StrategyContext


CORE = ["000217", "023145", "022888"]          # 黄金/油气/红利 各1/3
CORE_FALLBACK = {                              # 标的无数据时的族内替补
    "000217": ["002611", "002963", "004253"],
    "023145": ["020406", "021620", "021823", "019828"],
    "022888": ["021514", "017536"],
}
SAT_GROUPS = {
    "权益": ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
    "海外": ["160141"],
    "科技": ["024070", "023829", "020900"],
    "有色": ["004433"],
    "黄金股": ["021959", "021874"],
}
BOND_BUFFER = "006485"


class TrinitySandwichStrategy(Strategy):
    name = "Trinity三明治宏观"
    rebalance_freq = "monthly"
    params_schema = {
        "lookback_days": {"type": "int", "default": 250, "min": 60, "max": 500},
        "core_ratio": {"type": "float", "default": 0.4, "min": 0.1, "max": 0.8},
        "top_k": {"type": "int", "default": 2, "min": 1, "max": 3},
        "protect_halve": {"type": "int", "default": 1, "min": 0, "max": 1},
    }

    def _window(self, series: dict, date: str, n: int) -> list[float]:
        dates = sorted(d for d in series.keys() if d <= date)
        vals = []
        for d in dates[-(n + 1):]:
            px = series.get(d)
            if px and px > 0:
                vals.append(float(px))
        return vals

    def _ret(self, series: dict, date: str, days: int) -> float | None:
        vals = self._window(series, date, days)
        if len(vals) < 2 or vals[0] <= 0:
            return None
        return vals[-1] / vals[0] - 1.0

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        pool = {a["symbol"] for a in ctx.pool}
        lookback = self.params["lookback_days"]

        weights: dict[str, float] = {}

        # 1) 恒定核：主标的缺数据则用族内替补（有数据的选动量最强）
        core_on = []
        for sym in CORE:
            if sym in pool:
                m = self._ret(ctx.prices.get(sym, {}), date, lookback)
                if m is not None:
                    core_on.append(sym)
                    weights[sym] = weights.get(sym, 0.0) + self.params["core_ratio"] / 3
                    continue
            for fb in CORE_FALLBACK.get(sym, []):
                if fb in pool:
                    m = self._ret(ctx.prices.get(fb, {}), date, lookback)
                    if m is not None:
                        core_on.append(fb)
                        weights[fb] = weights.get(fb, 0.0) + self.params["core_ratio"] / 3
                        break

        # 2) 卫星：类内选强，取动量最强 top_k 类均分卫星预算
        ranked = []
        for cname, grp in SAT_GROUPS.items():
            bs, bm = None, -9e9
            for sym in grp:
                if sym not in pool:
                    continue
                m = self._ret(ctx.prices.get(sym, {}), date, lookback)
                if m is not None and m > bm:
                    bs, bm = sym, m
            if bs is not None and bm > 0.0:
                ranked.append((bs, bm))
        ranked.sort(key=lambda x: -x[1])
        k = min(self.params["top_k"], len(ranked))
        sat_budget = 1.0 - self.params["core_ratio"]
        if k and ranked:
            per = sat_budget / k
            for s, _m in ranked[:k]:
                weights[s] = weights.get(s, 0.0) + per

        # 3) 保护层：卫星全部转负 → 卫星预算减半退债（核恒持不动）
        if self.params.get("protect_halve", 1) and not ranked:
            weights[BOND_BUFFER] = weights.get(BOND_BUFFER, 0.0) + sat_budget * 0.5
        else:
            weights[BOND_BUFFER] = weights.get(BOND_BUFFER, 0.0) + (1.0 - sum(weights.values()))
        return {s: w for s, w in weights.items() if w > 1e-6}
