"""name: 动态多核宏观
description: 三核预算按126d风险调整动量动态分配(强者多拿,下限15%), 卫星同三核版
rebalance_freq: monthly
version: 1
version_note: 1.0-dynamic-core
factor_keys:
---

动态多核宏观 v1 —— 核预算不固定，按风险调整动量在金/油/红利间动态分配。

策略逻辑（月频）：
  1. 三核各算 126d 风险调整动量（收益/波动），>0 才有资格
  2. 预算按动量强度比例分配（softmax 风格），单核下限 15% 防独大
  3. 全部为负 → 100% 国开债
  4. 卫星与三核版相同：类内选强取最强 1 类
"""

from finkit_strategy import Strategy, StrategyContext


CORE_GROUPS = {
    "黄金核": ["000217", "002611", "002963", "004253", "021740"],
    "油气核": ["023145", "020406", "021620", "021823", "019828"],
    "红利核": ["022888", "021514", "017536"],
}
RISK_GROUPS = {
    "权益": ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
    "海外": ["160141"],
    "科技": ["024070", "023829", "020900"],
    "有色": ["004433"],
}
BOND_BUFFER = "006485"


class DynamicCoreStrategy(Strategy):
    name = "动态多核宏观"
    rebalance_freq = "monthly"
    params_schema = {
        "lookback_days": {"type": "int", "default": 126, "min": 60, "max": 500},
        "core_budget": {"type": "float", "default": 0.75, "min": 0.0, "max": 1.0},
        "risk_budget": {"type": "float", "default": 0.25, "min": 0.0, "max": 0.5},
        "min_core_weight": {"type": "float", "default": 0.15, "min": 0.0, "max": 0.4},
        "risk_scale": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
    }

    def _window(self, series: dict, date: str, n: int) -> list[float]:
        dates = sorted(d for d in series.keys() if d <= date)
        vals = []
        for d in dates[-(n + 1):]:
            px = series.get(d)
            if px and px > 0:
                vals.append(float(px))
        return vals

    def _risk_adj_mom(self, series: dict, date: str, days: int) -> float | None:
        vals = self._window(series, date, days)
        if len(vals) < days // 2 or vals[0] <= 0:
            return None
        rets = [vals[i + 1] / vals[i] - 1.0 for i in range(len(vals) - 1)]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        vol = var ** 0.5
        if vol < 1e-9:
            return None
        total = vals[-1] / vals[0] - 1.0
        return total / (vol * (len(rets) ** 0.5))

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        pool = {a["symbol"] for a in ctx.pool}
        lookback = self.params["lookback_days"]

        scores: dict[str, float] = {}
        syms: dict[str, str] = {}
        for cname, grp in CORE_GROUPS.items():
            bs, bm = None, -9e9
            for sym in grp:
                if sym not in pool:
                    continue
                m = self._risk_adj_mom(ctx.prices.get(sym, {}), date, lookback)
                if m is not None and m > bm:
                    bs, bm = sym, m
            if bs is not None and bm > 0.0:
                scores[bs] = bm
                syms[bs] = cname

        weights: dict[str, float] = {}
        if not scores:
            return {BOND_BUFFER: 1.0}

        total_score = sum(scores.values())
        budget = self.params["core_budget"]
        min_w = self.params["min_core_weight"]
        n = len(scores)
        floor_total = min_w * n
        if budget < floor_total:
            budget = floor_total
        free = budget - floor_total
        for s in scores:
            w = min_w + (free * scores[s] / total_score if total_score > 0 else free / n)
            weights[s] = weights.get(s, 0.0) + w

        risk_best = None
        for cname, grp in RISK_GROUPS.items():
            bs, bm = None, -9e9
            for sym in grp:
                if sym not in pool:
                    continue
                m = self._risk_adj_mom(ctx.prices.get(sym, {}), date, lookback)
                if m is not None and m > bm:
                    bs, bm = sym, m
            if bs is not None and bm > 0.0:
                if risk_best is None or bm > risk_best[1]:
                    risk_best = (bs, bm)
        if risk_best:
            weights[risk_best[0]] = weights.get(risk_best[0], 0.0) + self.params["risk_budget"]

        rs = self.params["risk_scale"]
        weights = {s: w * rs for s, w in weights.items()}
        weights[BOND_BUFFER] = weights.get(BOND_BUFFER, 0.0) + (1.0 - sum(weights.values()))
        return {s: w for s, w in weights.items() if w > 1e-6}
