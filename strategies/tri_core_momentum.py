"""name: 三核宏观动量
description: 黄金+油气+红利三核独立开关+科技卫星类内选强, 关闭预算转移给仍开的核, 全关退债
rebalance_freq: monthly
version: 1
version_note: 1.0-tri-core
factor_keys:
---

三核宏观动量 v1 —— 黄金/油气/红利三个低相关风险核，各自独立动量开关。

策略逻辑（月频）：
  1. 三核：黄金族选强(250d)、油气族选强、红利族选强，各自动量 > 0 开仓
  2. 任一核关闭 → 其预算按比例转给仍开着的核（而非死退债）
  3. 全部关闭 → 100% 0-3年国开债（防御）
  4. 卫星：权益/海外/科技/有色类内选强，动量>0 才入，预算给最强 1 类
  5. risk_scale 整体打折，剩余给国开债缓冲
"""

from finkit_strategy import Strategy, StrategyContext


CORE_GROUPS = {
    "黄金核": ["000217", "002611", "002963", "004253", "021740", "004253"],
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


class TriCoreMomentumStrategy(Strategy):
    name = "三核宏观动量"
    rebalance_freq = "monthly"
    params_schema = {
        "lookback_days": {"type": "int", "default": 250, "min": 60, "max": 500},
        "core_budget": {"type": "float", "default": 0.25, "min": 0.0, "max": 0.5},
        "risk_budget": {"type": "float", "default": 0.25, "min": 0.0, "max": 0.5},
        "risk_scale": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
        "buffer": {"type": "int", "default": 0, "min": 0, "max": 5},
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

        def best(group):
            bs, bm = None, -9e9
            for sym in group:
                if sym not in pool:
                    continue
                m = self._ret(ctx.prices.get(sym, {}), date, lookback)
                if m is not None and m > bm:
                    bs, bm = sym, m
            return bs, bm

        cores = {}
        for cname, grp in CORE_GROUPS.items():
            s, m = best(grp)
            if s is not None and m > 0.0:
                cores[s] = m

        weights: dict[str, float] = {}
        n_on = len(cores)
        if n_on:
            per = self.params["core_budget"] * 3 / n_on
            for s in cores:
                weights[s] = weights.get(s, 0.0) + per

        # 卫星：各类选强，动量最强的一类拿 risk_budget
        risk_best = None
        for cname, grp in RISK_GROUPS.items():
            s, m = best(grp)
            if s is not None and m > 0.0:
                if risk_best is None or m > risk_best[1]:
                    risk_best = (s, m, cname)
        if risk_best:
            weights[risk_best[0]] = weights.get(risk_best[0], 0.0) + self.params["risk_budget"]

        if not weights:
            weights[BOND_BUFFER] = 1.0
            return weights

        rs = self.params["risk_scale"]
        weights = {s: w * rs for s, w in weights.items()}
        weights[BOND_BUFFER] = weights.get(BOND_BUFFER, 0.0) + (1.0 - sum(weights.values()))
        return {s: w for s, w in weights.items() if w > 1e-6}
