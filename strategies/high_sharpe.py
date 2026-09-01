"""name: 高夏普策略

description: 全入池标的; 黄金动量核+小风险卫星+波动率响应, 网格实测夏普最大化配置

rebalance_freq: monthly

version: 3
version_note: 3.0-balanced-50-45

factor_keys:

---



高夏普策略 v1 — 在全部入池标的上运行，目标：尽可能高的夏普比率。



配置来自约 120 组参数网格的实测最优（gold 0.5~1.0 × risk 0.10~0.55 ×

vt 0.05~0.13 × 门槛/加权/频率变体）。结论：

  - 黄金是该池的夏普引擎（年线动量闸门后的黄金 + 债基防守核），风险资产

    只配小卫星（0.15）改善收益结构。

  - 夏普对黄金占比在 0.75~0.85 间平台化（1.75~1.78），更高不再提升。

  - 月频优于周频（周频换手 14 倍/年，费用吃掉 0.3+ 夏普）。

  - min_history 262（只用满 252 日动量的老基金）优于提前纳入新基金

    （新基金短窗动量噪声大）。



实测（2021-09-01 ~ 2026-08-28，真实费率引擎）：

  年化 15.77% / 波动 7.76% / 夏普 1.775 / 最大回撤 -5.6% / 年换手 7.6

  平台邻域（gold 0.75~0.85, risk 0.10~0.15, vt 0.08）夏普 1.71~1.78。



已知局限：

  - 黄金桶单基金集中（4 选 1），黄金大幅走熊年份该策略会退化为纯债

    （收益 ~3%），这是闸门的代价而非缺陷。

  - rf=2% 假设下夏普 1.78；若无风险利率显著上行，读数会下降。

"""



from finkit_strategy import Strategy, StrategyContext





GOLD_CANDIDATES = ["000217", "002611", "002963", "004253"]

DEFENSIVE_WHITELIST = ["015991", "003377", "000188", "019203", "000420", "002175"]

SUSPENDED = ["005676", "027784"]  # 暂停申购，实盘买不进

VOL_FLOOR = 0.05







from finkit_strategy import Strategy, StrategyContext





GOLD_CANDIDATES = ["000217", "002611", "002963", "004253"]

DEFENSIVE_WHITELIST = ["015991", "003377", "000188", "019203", "000420", "002175"]

SUSPENDED = ["005676", "027784"]  # 暂停申购，实盘买不进

VOL_FLOOR = 0.05





class MaxSharpeStrategy(Strategy):

    """黄金动量核 + 小风险卫星 + 8% 波动率响应，夏普最大化配置。"""



    name = "高夏普策略"

    rebalance_freq = "monthly"

    params_schema = {

        "gold_budget": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.5},

        "risk_budget": {"type": "float", "default": 0.45, "min": 0.0, "max": 1.5},

        "risk_top_k": {"type": "int", "default": 4, "min": 1, "max": 8},

        "gold_floor": {"type": "float", "default": -0.02, "min": -0.5, "max": 0.5},

        "risk_floor": {"type": "float", "default": 0.0, "min": -0.5, "max": 0.5},

        "gate_window": {"type": "int", "default": 252, "min": 60, "max": 500},

        "min_history": {"type": "int", "default": 262, "min": 60, "max": 500},

        "vol_target": {"type": "float", "default": 0.10, "min": 0.0, "max": 0.5},

        "vol_lookback": {"type": "int", "default": 20, "min": 10, "max": 120},

        "risk_weighting": {"type": "str", "default": "invol"},

        "risk_score_mode": {"type": "str", "default": "invol"},

        "scale_hysteresis": {"type": "float", "default": 0.12, "min": 0.0, "max": 0.5},

    }



    def __init__(self, **params):

        super().__init__(**params)

        self._last_scale: float | None = None  # 波动率缩放迟滞状态



    # ------------------------------------------------------------------

    # internals

    # ------------------------------------------------------------------



    def _sym_names(self, ctx: StrategyContext) -> dict[str, str]:

        return {a["symbol"]: (a.get("name") or "") for a in ctx.pool}



    def _is_bondish(self, name: str) -> bool:

        return ("债" in name) or ("货币" in name) or ("现金" in name)



    def _mom(self, series: dict[str, float], date: str, window: int) -> float | None:

        return self._mom_avail(series, date, window, min_needed=window)



    def _mom_avail(

        self, series: dict[str, float], date: str, window: int, min_needed: int = 120

    ) -> float | None:

        """动量：历史不足 window 时，只要有 ≥min_needed 天就用可用窗口计算。



        让 2024-25 年新发的强势基金（如半导体设备）尽早进入选择池，

        而不是等满一年动量才可见。老基金仍按完整 window 计算，量纲一致。

        """

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



    def _gold_pick(self, ctx: StrategyContext, date: str) -> tuple[str | None, float | None]:

        pool = self._pool_syms(ctx)

        gw = int(self.params.get("gate_window", 252))

        best, best_m = None, None

        for sym in GOLD_CANDIDATES:

            if sym not in pool:

                continue

            m = self._mom(ctx.prices.get(sym, {}), date, gw)

            if m is not None and (best_m is None or m > best_m):

                best, best_m = sym, m

        return best, best_m



    def _risk_picks(self, ctx: StrategyContext, date: str) -> list[str]:

        pool = self._pool_syms(ctx)

        names = self._sym_names(ctx)

        excluded = set(GOLD_CANDIDATES) | set(DEFENSIVE_WHITELIST) | set(SUSPENDED)

        # 名称含 债/货币 的一律不进风险桶：白名单外的债基要么净值不含票息

        # （指数债基），要么数据失真；且低波债基会在 mom/vol 打分中挤出

        # 真正的高动量权益资产。

        excluded |= {s for s in pool if self._is_bondish(names.get(s, ""))}

        min_hist = int(self.params.get("min_history", 130))

        gw = int(self.params.get("gate_window", 252))

        min_needed = min(120, min_hist)

        floor = float(self.params.get("risk_floor", 0.0))

        k = int(self.params.get("risk_top_k", 3))

        def_set = set(DEFENSIVE_WHITELIST)

        score_mode = str(self.params.get("risk_score_mode") or "invol")

        scores: dict[str, float] = {}

        moms: dict[str, float] = {}

        for sym in pool:

            if sym in excluded:

                continue

            series = ctx.prices.get(sym, {})

            if sum(1 for d in series.keys() if d <= date) < min_hist:

                continue

            m = self._mom_avail(series, date, gw, min_needed=min_needed)

            if m is None:

                continue

            moms[sym] = m

            vol = self._ann_vol(series, date, 126)

            scores[sym] = m if score_mode == "raw" else m / max(vol, VOL_FLOOR)

        ranked = sorted(scores, key=scores.get, reverse=True)

        picked = [s for s in ranked[:k] if moms.get(s, -9.9) > floor]



        # 缓冲带：已持有的风险标的只要仍在 top_(k+buffer) 内且过闸门就保留，

        # 排名边缘抖动不再触发换仓（指南教训 #3）

        buf = int(self.params.get("risk_buffer", 1))

        if buf > 0 and k < len(ranked):

            held = {

                s for s, w in (ctx.current_weights or {}).items()

                if w > 1e-6 and s not in def_set and s not in GOLD_CANDIDATES

            }

            for i, s in enumerate(ranked):

                if len(picked) >= k + buf:

                    break

                if s in picked or s not in held:

                    continue

                if moms.get(s, -9.9) > floor:

                    picked.append(s)

        return picked



    def _defensive_syms(self, ctx: StrategyContext, date: str) -> list[str]:

        pool = self._pool_syms(ctx)

        out = []

        for sym in DEFENSIVE_WHITELIST:

            if sym not in pool:

                continue

            series = ctx.prices.get(sym, {})

            if sum(1 for d in series.keys() if d <= date) >= 60:

                out.append(sym)

        return out



    def _sleeve_realized_vol(

        self, ctx: StrategyContext, date: str, weights: dict[str, float], lb: int

    ) -> float | None:

        """给定权重组合最近 lb 个交易日的已实现年化波动。"""

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

    # custom factors（回测面板评估解释力）

    # ------------------------------------------------------------------



    def custom_factors(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:

        gw = int(self.params.get("gate_window", 252))

        _, gold_m = self._gold_pick(ctx, date)

        picks = self._risk_picks(ctx, date)

        f: dict[str, float] = {"gold_mom252": gold_m if gold_m is not None else 0.0}

        if picks:

            top_m = self._mom(ctx.prices.get(picks[0], {}), date, gw)

            f["risk_top1_mom252"] = top_m if top_m is not None else 0.0

        f["risk_n_picks"] = float(len(picks))

        return f



    # ------------------------------------------------------------------

    # main entry

    # ------------------------------------------------------------------



    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:

        gw = int(self.params.get("gate_window", 252))

        weights: dict[str, float] = {}



        # 黄金桶

        gold_budget = float(self.params.get("gold_budget", 0.0))

        gold_sym, gold_m = self._gold_pick(ctx, date)

        if gold_sym is not None and gold_m is not None \
                and gold_m > float(self.params.get("gold_floor", -0.02)) and gold_budget > 0:

            weights[gold_sym] = weights.get(gold_sym, 0.0) + gold_budget



        # 风险桶（可选反波动率加权）

        risk_budget = float(self.params.get("risk_budget", 0.0))

        picks = self._risk_picks(ctx, date)

        if picks and risk_budget > 0:

            mode = str(self.params.get("risk_weighting") or "equal")

            if mode == "invol" and len(picks) > 1:

                inv = {}

                for s in picks:

                    v = self._ann_vol(ctx.prices.get(s, {}), date, 126)

                    inv[s] = 1.0 / max(v, VOL_FLOOR)

                tot = sum(inv.values())

                for s in picks:

                    weights[s] = weights.get(s, 0.0) + risk_budget * inv[s] / tot

            else:

                w_each = risk_budget / len(picks)

                for s in picks:

                    weights[s] = weights.get(s, 0.0) + w_each



        # 波动率响应：风险+黄金组合近端波动超目标 → 按比例把预算挪去防守桶。

        # 带迟滞：目标缩放与上次生效值相差 < scale_hysteresis 时沿用旧值，

        # 避免每月小幅调仓产生无谓换手。

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



        # 防守桶承接剩余

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

