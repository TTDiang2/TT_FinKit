"""name: 高夏普策略
description: 分散动量引擎——全风险资产+黄金按 sharpe-momentum 竞争分配, 软闸门, 不再黄金独大
rebalance_freq: monthly
version: 2
version_note: 2.0-multi-engine
factor_keys:
---

高夏普策略 v2 — 修复 v1「黄金独大」缺陷。

v1 问题：gold_budget=0.8 绑死黄金，黄金动量闸门关闭时 80% 预算全部退到
债基 → 2026.01-09 黄金横盘期策略空转。诊断确认：本质是「高黄金」策略。

v2 结构（黄金降级为参与竞争的一类资产）：
  1. 候选池：全池排除债/货币/防守白名单/暂停申购 + 最强黄金 1 只
     （黄金作为普通候选与其他风险资产同台竞争，不再有固定预算）
  2. 打分：sharpe-momentum = 252 日动量 / 126 日年化波动
  3. 软闸门：动量 > mom_floor（默认 -0.05，比 v1 的 0 门槛更宽松，
     减少反复开关打脸）；候选全灭 → 100% 债基防守
  4. 分配：top_k（默认 4）只按反波动加权分 core_budget（默认 0.9）
     —— 黄金强时它自然拿大头（保留 v1 优势），黄金横盘时其他
     强势风险资产自动顶上
  5. 波动率响应：组合近端波动超 vol_target → 按比例缩去债基
     （迟滞防抖），剩余全部防守白名单承接
  6. min_history 262 的老基金偏好保留，但新基金用可用窗口
     （_mom_avail 语义与 v1 一致）

参数（params_schema）：
  - core_budget: 风险预算总额，默认 0.90
  - top_k: 入选资产数，默认 4
  - mom_floor: 软闸门（252 日动量下限），默认 -0.05
  - include_gold: 是否纳入黄金候选，默认 1
  - vol_target / vol_lookback / scale_hysteresis: 波动率响应（同 v1）
"""
from finkit_strategy import Strategy, StrategyContext

GOLD_CANDIDATES = ["000217", "002611", "002963", "004253"]
DEFENSIVE_WHITELIST = ["015991", "003377", "000188", "019203", "000420", "002175"]
SUSPENDED = ["005676", "027784"]
VOL_FLOOR = 0.05


class MultiEngineStrategy(Strategy):
    """分散动量引擎：全风险资产+黄金按 sharpe-momentum 竞争分配。"""

    name = "高夏普策略"
    rebalance_freq = "monthly"
    params_schema = {
        "core_budget": {"type": "float", "default": 0.90, "min": 0.0, "max": 1.0},
        "top_k": {"type": "int", "default": 4, "min": 1, "max": 8},
        "mom_floor": {"type": "float", "default": -0.05, "min": -0.5, "max": 0.5},
        "include_gold": {"type": "int", "default": 1, "min": 0, "max": 1},
        "gate_window": {"type": "int", "default": 252, "min": 60, "max": 500},
        "min_history": {"type": "int", "default": 262, "min": 60, "max": 500},
        "vol_target": {"type": "float", "default": 0.10, "min": 0.0, "max": 0.5},
        "vol_lookback": {"type": "int", "default": 20, "min": 10, "max": 120},
        "scale_hysteresis": {"type": "float", "default": 0.12, "min": 0.0, "max": 0.5},
    }

    def __init__(self, **params):
        super().__init__(**params)
        self._last_scale: float | None = None

    # ------------------------------------------------------------------
    # internals（与 v1 同语义的通用件）
    # ------------------------------------------------------------------

    def _sym_names(self, ctx: StrategyContext) -> dict[str, str]:
        return {a["symbol"]: (a.get("name") or "") for a in ctx.pool}

    def _is_bondish(self, name: str) -> bool:
        return ("债" in name) or ("货币" in name) or ("现金" in name)

    def _mom_avail(self, series: dict[str, float], date: str, window: int,
                   min_needed: int = 120) -> float | None:
        dates = sorted(d for d in series.keys() if d <= date)
        if len(dates) < 2:
            return None
        eff = min(window, len(dates) - 1)
        if eff < min_needed:
            return None
        win = dates[-(eff + 1):]
        base, latest = series.get(win[0], 0.0), series.get(win[-1], 0.0)
        if base <= 0:
            return None
        return latest / base - 1.0

    def _ann_vol(self, series: dict[str, float], date: str, window: int) -> float:
        dates = sorted(d for d in series.keys() if d <= date)
        win = dates[-(window + 1):]
        rets = []
        for a, b in zip(win, win[1:]):
            p0, p1 = series.get(a, 0.0), series.get(b, 0.0)
            if p0 > 0 and p1 > 0:
                rets.append(p1 / p0 - 1.0)
        if len(rets) < 10:
            return VOL_FLOOR
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        return max((var ** 0.5) * (252 ** 0.5), VOL_FLOOR)

    def _pool_syms(self, ctx: StrategyContext) -> set[str]:
        return {a["symbol"] for a in ctx.pool}

    def _candidates(self, ctx: StrategyContext, date: str) -> dict[str, float]:
        """候选 → sharpe-momentum 打分。黄金作为普通候选参与（取最强 1 只）。"""
        pool = self._pool_syms(ctx)
        names = self._sym_names(ctx)
        gw = int(self.params.get("gate_window", 252))
        min_hist = int(self.params.get("min_history", 262))
        min_needed = min(120, min_hist)
        include_gold = bool(int(self.params.get("include_gold", 1)))
        excluded = set(DEFENSIVE_WHITELIST) | set(SUSPENDED)
        excluded |= {s for s in pool if self._is_bondish(names.get(s, ""))}
        if not include_gold:
            excluded |= set(GOLD_CANDIDATES)

        scores: dict[str, float] = {}
        best_gold, best_gold_m = None, None
        for sym in pool:
            is_gold = sym in GOLD_CANDIDATES
            if sym in excluded and not is_gold:
                continue
            series = ctx.prices.get(sym, {})
            if sum(1 for d in series.keys() if d <= date) < min_hist:
                continue
            m = self._mom_avail(series, date, gw, min_needed=min_needed)
            if m is None:
                continue
            if is_gold:
                if best_gold_m is None or m > best_gold_m:
                    best_gold, best_gold_m = sym, m
                continue
            vol = self._ann_vol(series, date, 126)
            scores[sym] = m / max(vol, VOL_FLOOR)

        if include_gold and best_gold is not None and best_gold_m is not None:
            vol = self._ann_vol(ctx.prices.get(best_gold, {}), date, 126)
            scores[best_gold] = best_gold_m / max(vol, VOL_FLOOR)
        return scores

    def _defensive_syms(self, ctx: StrategyContext, date: str) -> list[str]:
        pool = self._pool_syms(ctx)
        return [s for s in DEFENSIVE_WHITELIST if s in pool
                and sum(1 for d in ctx.prices.get(s, {}).keys() if d <= date) >= 60]

    def _sleeve_realized_vol(self, ctx: StrategyContext, date: str,
                             weights: dict[str, float], lb: int) -> float | None:
        active = {s: w for s, w in weights.items() if w > 0}
        if not active:
            return None
        total_w = sum(active.values()) or 1.0
        rets_by_sym: dict[str, dict[str, float]] = {}
        common: set[str] | None = None
        for sym in active:
            series = ctx.prices.get(sym, {})
            dates = sorted(d for d in series.keys() if d <= date)[-(lb + 1):]
            rmap = {d2: series[d2] / series[d1] - 1.0
                    for d1, d2 in zip(dates, dates[1:]) if series.get(d1, 0) > 0}
            rets_by_sym[sym] = rmap
            ds = set(rmap.keys())
            common = ds if common is None else (common & ds)
        if not common or len(common) < 10:
            return None
        port = []
        for d in sorted(common):
            port.append(sum((active[s] / total_w) * rets_by_sym[s][d]
                            for s in active if d in rets_by_sym[s]))
        mean = sum(port) / len(port)
        var = sum((r - mean) ** 2 for r in port) / (len(port) - 1)
        return (var ** 0.5) * (252 ** 0.5)

    # ------------------------------------------------------------------
    # main entry
    # ------------------------------------------------------------------

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        weights: dict[str, float] = {}
        scores = self._candidates(ctx, date)
        mom_by_sym: dict[str, float] = {}
        gw = int(self.params.get("gate_window", 252))
        for sym in scores:
            m = self._mom_avail(ctx.prices.get(sym, {}), date, gw,
                                min_needed=min(120, int(self.params.get("min_history", 262))))
            if m is not None:
                mom_by_sym[sym] = m

        # 软闸门过滤
        floor = float(self.params.get("mom_floor", -0.05))
        ranked = sorted(scores, key=scores.get, reverse=True)
        picked = [s for s in ranked if mom_by_sym.get(s, -9.9) > floor]

        # top_k 入选按反波动加权分 core_budget
        k = int(self.params.get("top_k", 4))
        core_budget = float(self.params.get("core_budget", 0.90))
        picked = picked[:k]
        if picked and core_budget > 0:
            inv = {}
            for s in picked:
                v = self._ann_vol(ctx.prices.get(s, {}), date, 126)
                inv[s] = 1.0 / max(v, VOL_FLOOR)
            tot = sum(inv.values())
            for s in picked:
                weights[s] = core_budget * inv[s] / tot

        # 波动率响应（同 v1：超目标按比例缩去债基，迟滞防抖）
        vt = float(self.params.get("vol_target", 0.0) or 0.0)
        defensive = self._defensive_syms(ctx, date)
        def_set = set(defensive)
        risky = {s: w for s, w in weights.items() if s not in def_set}
        if vt > 0 and risky and defensive:
            lb = int(self.params.get("vol_lookback", 20))
            realized = self._sleeve_realized_vol(ctx, date, risky, lb)
            if realized is not None and realized > vt:
                scale = min(1.0, vt / realized)
            else:
                scale = 1.0
            hyst = float(self.params.get("scale_hysteresis", 0.12))
            if self._last_scale is not None and abs(scale - self._last_scale) < hyst:
                scale = self._last_scale
            self._last_scale = scale
            if scale < 1.0:
                freed = sum(risky.values()) * (1.0 - scale)
                weights = {s: (w * scale if s in risky else w) for s, w in weights.items()}
                w_each = freed / len(defensive)
                for s in defensive:
                    weights[s] = weights.get(s, 0.0) + w_each

        # 防守桶承接剩余；候选全灭 → 100% 防守
        leftover = 1.0 - sum(weights.values())
        if defensive and leftover > 1e-6:
            w_each = leftover / len(defensive)
            for s in defensive:
                weights[s] = weights.get(s, 0.0) + w_each
        elif not defensive and leftover > 1e-6:
            total = sum(weights.values())
            if total > 0:
                weights = {s: w / total for s, w in weights.items()}

        if not weights:
            return None
        return weights
