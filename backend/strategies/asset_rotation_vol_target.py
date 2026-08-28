"""name: 大类资产动量轮动
description: 类内选强+多周期风险调整动量+波动率目标(国开债缓冲)+周频熔断
rebalance_freq: weekly
version_note: 2.0.0-vol-target
factor_keys:
---

大类资产动量轮动 v2 — 在「大类资产代表」池上运行的波动率目标版。

策略逻辑（每个调仓日，默认每周）：
  1. 类内选强：六大类（权益/海外/黄金/油气/有色/利率债）内按 126 日
     风险调整动量（收益/波动）选出各类代表
  2. 类间排序：代表的多周期动量（21/63/126/252 日均值）
  3. 入选：动量为正的类取前 top_k；全部为负 → 100% 0-3年国开债（防御态，
     等效紧急调仓——周频检查保证最晚一周内退出风险资产）
  4. 波动率目标：入选类等权 σ_est = sqrt(mean σi²)（20 日年化），
     与 0-3年国开债(σ_bond)联合解出风险权重 w_r 使组合 σ≈vol_target，
     其余权重全部给国开债缓冲（场外基金无杠杆，w_r≤1 天然封顶）
  5. 缓冲带：已持有类仍处 top_(k+buffer) 且动量为正则保留

实测（2021-09 ~ 2026-08，大类资产代表池 21 只 C 份额）：
  见 scripts/tune_macro_momentum.py 输出

参数（params.schema）：
  - vol_target: 组合年化波动目标，默认 0.05
  - top_k: 风险类最多同时持有几个，默认 3
  - lookback_days: 类代表动量/波动窗口，默认 126
  - buffer: 类排名缓冲带宽度，默认 1
"""

from finkit_strategy import Strategy, StrategyContext


GROUPS = {
    "权益": ["001549", "001593", "002903", "001589", "002977", "004408", "012757"],
    "海外": ["160141"],
    "黄金": ["000217", "002611", "002963", "004253"],
    "油气": ["019828", "020105", "020406", "021620"],
    "有色": ["004433"],
    "利率债": ["003377", "006452", "006485", "000396"],
}
BOND_BUFFER = "006485"   # 0-3年国开债C：低波缓冲/防御资产


class AssetRotationVolTargetStrategy(Strategy):
    """大类资产动量轮动 v3：金债核心 + 动量开关卫星（核心-卫星结构）。"""

    name = "大类资产动量轮动"
    rebalance_freq = "monthly"
    params_schema = {
        "gold_budget": {"type": "float", "default": 0.35, "min": 0.0, "max": 0.6},
        "equity_budget": {"type": "float", "default": 0.25, "min": 0.0, "max": 0.6},
        "oil_budget": {"type": "float", "default": 0.10, "min": 0.0, "max": 0.4},
        "risk_scale": {"type": "float", "default": 0.5, "min": 0.1, "max": 1.0},
        "lookback_days": {"type": "int", "default": 250, "min": 20, "max": 500},
        "buffer": {"type": "int", "default": 2, "min": 0, "max": 3},
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

        def class_best(cname: str) -> tuple[str | None, float]:
            best_sym, best_m = None, -9e9
            for sym in GROUPS.get(cname, []):
                if sym not in pool:
                    continue
                m = self._ret(ctx.prices.get(sym, {}), date, lookback)
                if m is not None and m > best_m:
                    best_sym, best_m = sym, m
            return best_sym, best_m

        gold_sym, gold_m = class_best("黄金")
        eq_sym, eq_m = class_best("权益")
        oil_sym, oil_m = class_best("油气")
        os_sym, os_m = class_best("海外")

        # 权益预算给境内/海外中动量更强的一方
        eq_final_sym, eq_final_m = (eq_sym, eq_m)
        if os_sym and (eq_sym is None or os_m > eq_m):
            eq_final_sym, eq_final_m = os_sym, os_m

        weights: dict[str, float] = {}
        gold_on = gold_sym is not None and gold_m > -0.02      # 迟滞：-2% 才关
        eq_on = eq_final_sym is not None and eq_final_m > 0.0
        oil_on = oil_sym is not None and oil_m > 0.0
        if gold_on:
            weights[gold_sym] = self.params["gold_budget"]
        if eq_on:
            weights[eq_final_sym] = self.params["equity_budget"]
        if oil_on:
            weights[oil_sym] = self.params["oil_budget"]
        # 权益关闭时预算并入黄金（股金负相关：权益熊=金牛避险承接）
        if not eq_on and gold_on:
            weights[gold_sym] = weights.get(gold_sym, 0.0) + self.params["equity_budget"]
        # 黄金也关闭（真通胀/利率冲击）→ 全部进国开债
        risk_scale = self.params.get("risk_scale", 1.0)
        weights = {s: w * risk_scale for s, w in weights.items()}
        risk_total = sum(weights.values())
        weights[BOND_BUFFER] = weights.get(BOND_BUFFER, 0.0) + (1.0 - risk_total)
        return {s: w for s, w in weights.items() if w > 1e-6}
