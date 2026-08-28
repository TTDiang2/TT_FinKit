"""name: 大类资产动量轮动
description: 核心卫星宏观动量——各类选最强C+动量开关(黄金迟滞)+权益二选一+风险预算打折+利率债缓冲
rebalance_freq: monthly
version: 3
version_note: 3.0-core-satellite
factor_keys:
---

大类资产动量轮动 v3（核心-卫星）——在「大类资产代表」池上运行。

策略逻辑（每个调仓日，月频）：
  1. 类内选强：权益/海外/黄金/油气/有色各类内按 250 日纯动量选最强者
  2. 动量开关：类动量 > 0 才开仓；黄金带 -2% 迟滞防频繁开关
  3. 预算分配：黄金 gold_budget + 权益 equity_budget(给境内/海外较强方)
     + 油气 oil_budget
  4. 权益全关时其预算并入黄金（股金负相关承接）
  5. risk_scale 整体风险预算打折，剩余全部给 0-3 年国开债 C 缓冲
  6. buffer 缓冲带（百分点）减少无效换仓

实测（2021-09 ~ 2026-08，大类资产代表 21 只 C 份额，定稿参数）：
  7.24% 年化 / 5.72% 波动 / 夏普 0.92 / 最大回撤 -9.3%
  （rs=1 激进档：12.91%/10.26%/1.06/-16.4%）

参数（params_schema）：
  - lookback_days: 类内动量窗口，默认 250
  - gold_budget: 黄金类风险预算，默认 0.5
  - equity_budget: 权益类风险预算（境内+海外），默认 0.2
  - oil_budget: 油气类风险预算，默认 0.1
  - risk_scale: 整体风险预算打折，默认 0.5
  - buffer: 换仓缓冲带（百分点），默认 2
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
"gold_budget": {"type": "float", "default": 0.5, "min": 0.0, "max": 0.6},
"equity_budget": {"type": "float", "default": 0.2, "min": 0.0, "max": 0.6},
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
