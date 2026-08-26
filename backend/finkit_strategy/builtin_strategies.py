"""4 built-in strategies + SMA timing strategy."""
from finkit_strategy import Strategy, StrategyContext


class EqualWeightStrategy(Strategy):
    """等权再平衡：每月末等权持有 universe 中所有标的"""
    name = "等权再平衡"
    description = "每月末等权持有 universe 中所有标的，再平衡至等权"
    rebalance_freq = "monthly"
    params_schema = {}

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        ids = self.universe(ctx)
        if not ids:
            return None
        w = 1.0 / len(ids)
        return {aid: w for aid in ids}


class VolatilityInverseStrategy(Strategy):
    """波动率倒数加权：权重与年化波动率成反比"""
    name = "波动率倒数"
    description = "月末计算 lookback 窗口波动率，权重与波动率成反比（下限 1%）"
    rebalance_freq = "monthly"
    params_schema = {
        "lookback": {"type": "int", "default": 60, "min": 20, "max": 500},
        "min_weight": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.1},
    }

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        ids = self.universe(ctx)
        if not ids:
            return None
        vol = ctx.volatility(ids, lookback=self.params["lookback"])
        min_w = self.params["min_weight"]
        raw_weights = {aid: 1.0 / max(v, 1e-6) for aid, v in vol.items()}
        total = sum(raw_weights.values())
        if total == 0:
            return None
        return {aid: max(w / total, min_w) for aid, w in raw_weights.items()}


class MomentumRotationStrategy(Strategy):
    """动量轮动：每月末选 lookback 累计收益前 N 名等权持有"""
    name = "动量轮动"
    description = "每月末按 lookback 累计收益选前 N 名等权持有"
    rebalance_freq = "monthly"
    params_schema = {
        "top_n": {"type": "int", "default": 3, "min": 1, "max": 20},
        "lookback_days": {"type": "int", "default": 120, "min": 20, "max": 500},
    }

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        ids = self.universe(ctx)
        if not ids:
            return None
        mom = ctx.momentum(ids, lookback=self.params["lookback_days"])
        top = sorted(mom, key=mom.get, reverse=True)[: self.params["top_n"]]
        if not top:
            return None
        w = 1.0 / len(top)
        return {aid: w for aid in top}


class RiskParityStrategy(Strategy):
    """股债风险平价：权益与债券按风险贡献各 50%"""
    name = "风险平价"
    description = "权益(沪深300)与债券(国债ETF)按风险贡献各 50% 配置"
    rebalance_freq = "monthly"
    params_schema = {
        "equity_symbol": {"type": "str", "default": "000300"},
        "bond_symbol": {"type": "str", "default": "511010"},
        "lookback": {"type": "int", "default": 120, "min": 20, "max": 500},
        "target_rc": {"type": "float", "default": 0.5},
    }

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        eq = self.params["equity_symbol"]
        bd = self.params["bond_symbol"]
        vol = ctx.volatility([eq, bd], lookback=self.params["lookback"])
        eq_vol = vol.get(eq, 0.01)
        bd_vol = vol.get(bd, 0.01)
        if eq_vol < 1e-6 or bd_vol < 1e-6:
            return None
        target_rc = self.params["target_rc"]
        w_eq = min(target_rc / eq_vol, 0.9)
        w_bd = min(target_rc / bd_vol, 0.9)
        total = w_eq + w_bd
        return {eq: w_eq / total, bd: w_bd / total}


class SMATimingStrategy(Strategy):
    """MA 均线择时：收盘价在 MA 上方全仓，跌破 MA 空仓。

    仅适用于单一标的的场景（如 000217）。
    参数 ma_days 控制均线窗口。
    """
    name = "MA 均线择时"
    description = "收盘价上穿 N 日均线全仓，下穿空仓。仅适用于单一标的。"
    rebalance_freq = "monthly"
    params_schema = {
        "ma_days": {"type": "int", "default": 20, "min": 5, "max": 250},
    }

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        ids = self.universe(ctx)
        if not ids:
            return None
        aid = ids[0]
        price_series = ctx.prices.get(aid, {})
        if not price_series:
            return None
        # 找到 date 当日或之前最近的价格
        sorted_dates = sorted(d for d in price_series.keys() if d <= date)
        if not sorted_dates:
            return None
        current_price = price_series[sorted_dates[-1]]
        # 计算 MA(ma_days)
        ma_days = self.params["ma_days"]
        ma = self._sma(price_series, sorted_dates[-1], ma_days)
        if ma is None:
            return None
        if current_price > ma:
            return {aid: 1.0}
        else:
            return {aid: 0.0}

    def _sma(self, price_series: dict[str, float], end_date: str, n: int) -> float | None:
        """end_date 当日（含）向前取 n 个交易日，求简单平均。"""
        dates = sorted(d for d in price_series.keys() if d <= end_date)
        if len(dates) < n:
            return None
        vals = [price_series[d] for d in dates[-n:]]
        return sum(vals) / n


def _pct_returns(series: dict[str, float], dates: list[str]) -> list[float]:
    out = []
    for a, b in zip(dates, dates[1:]):
        p0, p1 = series.get(a, 0.0), series.get(b, 0.0)
        if p0 > 0 and p1 > 0:
            out.append(p1 / p0 - 1.0)
    return out


VOL_FLOOR = 0.05  # 年化波动下限: 防止近零波动资产的动量/波动分数爆炸


class AssetRotationStrategy(Strategy):
    """多周期风险调整动量轮动 + 双重风控（绝对动量 + 波动率目标）。"""

    name = "大类资产动量轮动"
    rebalance_freq = "monthly"
    params_schema = {
        "symbols": {"type": "str", "default": "000217,000667,002910,006432,378546"},
        "windows": {"type": "str", "default": "21,63,126,252"},
        "top_k": {"type": "int", "default": 3, "min": 1, "max": 6},
        "buffer": {"type": "int", "default": 1, "min": 0, "max": 3},
        "momentum_floor": {"type": "float", "default": -0.02, "min": -1.0, "max": 0.5},
        "defensive": {"type": "str", "default": "006432"},
        "vol_lookback": {"type": "int", "default": 20, "min": 5, "max": 120},
        "vol_target": {"type": "float", "default": 0.15, "min": 0.0, "max": 0.5},
    }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _candidates(self, ctx: StrategyContext) -> list[str]:
        pool_symbols = {a["symbol"] for a in ctx.pool}
        wanted = [s.strip() for s in str(self.params.get("symbols", "")).split(",") if s.strip()]
        return [s for s in wanted if s in pool_symbols]

    def _window_mom_vol(self, series: dict[str, float], date: str, window: int) -> tuple[float, float] | None:
        """(momentum, annualized vol) over the last `window` trading days."""
        dates = sorted(d for d in series.keys() if d <= date)
        if len(dates) < 2:
            return None
        win_dates = dates[-(window + 1):]
        if len(win_dates) < 2:
            return None
        base, latest = series[win_dates[0]], series[win_dates[-1]]
        if not base or base <= 0:
            return None
        mom = latest / base - 1.0
        rets = _pct_returns(series, win_dates)
        if len(rets) < 5:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        vol = (var ** 0.5) * (252 ** 0.5)
        return mom, vol

    def _scores(self, ctx: StrategyContext, date: str) -> dict[str, float]:
        """Multi-window risk-adjusted momentum score per candidate."""
        windows_raw = self.params.get("windows") or "21,63,126,252"
        windows = [int(w) for w in str(windows_raw).split(",") if w.strip()]
        scores: dict[str, list[float]] = {}
        for sym in self._candidates(ctx):
            series = ctx.prices.get(sym, {})
            parts: list[float] = []
            for w in windows:
                mv = self._window_mom_vol(series, date, w)
                if mv is None:
                    continue
                mom, vol = mv
                vol = max(vol, VOL_FLOOR)
                # 区间夏普式动量：收益 / (年化波动 * sqrt(窗口)) 归一化到同量纲
                parts.append(mom / (vol * (w ** 0.5)))
            if parts:
                scores[sym] = sum(parts) / len(parts)
        return scores

    # ------------------------------------------------------------------
    # custom factors (explanatory-power evaluation in the backtest panel)
    # ------------------------------------------------------------------

    def custom_factors(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        mom = self._raw_momentum(ctx, date)
        if not mom:
            return None
        vals = list(mom.values())
        held_mom = [mom[s] for s, w in (ctx.current_weights or {}).items() if w > 1e-6 and s in mom]
        factors = {
            "top1_momentum": max(vals),
            "breadth_pos": sum(1 for v in vals if v > 0) / len(vals),
            "held_momentum": sum(held_mom) / len(held_mom) if held_mom else 0.0,
        }
        # macro rate tilts from the factor library (20d trend of yields)
        fv = getattr(ctx, "factor_values", {}) or {}
        for key, name in (("us_rate", "rate_tilt_gold"), ("cn_rate", "rate_tilt_bond")):
            ser = fv.get(key) or {}
            dates = sorted(d for d in ser.keys() if d <= date)
            if len(dates) >= 21:
                factors[name] = ser[dates[-1]] - ser[dates[-21]]
        return factors

    def _raw_momentum(self, ctx: StrategyContext, date: str) -> dict[str, float]:
        mom: dict[str, float] = {}
        for sym in self._candidates(ctx):
            mv = self._window_mom_vol(ctx.prices.get(sym, {}), date, 126)
            if mv is not None:
                mom[sym] = mv[0]
        return mom

    # ------------------------------------------------------------------
    # main entry
    # ------------------------------------------------------------------

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        scores = self._scores(ctx, date)
        if not scores:
            return None

        ranked = sorted(scores, key=scores.get, reverse=True)

        # absolute momentum gate on the strongest candidate's 126d momentum:
        # 无趋势时不空仓，而是切到防守资产（债基）吃票息——
        # 空仓收益为 0 必然跑输无风险利率，防守切换消灭"零收益躺平期"
        raw_mid = self._raw_momentum(ctx, date)
        floor = self.params.get("momentum_floor", 0.0)
        leader_ok = raw_mid.get(ranked[0], 0.0) >= floor if raw_mid else True

        k = self.params["top_k"]
        buffer_n = self.params.get("buffer", 0)
        keep = set(ranked[:k]) if leader_ok else set()
        rank = {sym: i for i, sym in enumerate(ranked)}
        for sym, w in (ctx.current_weights or {}).items():
            if w > 1e-6 and sym in rank and rank[sym] < k + buffer_n and leader_ok:
                keep.add(sym)

        weights: dict[str, float]
        if not keep:
            defensive = [s.strip() for s in str(self.params.get("defensive", "")).split(",") if s.strip()]
            defensive = [s for s in defensive if s in ctx.prices]
            if defensive:
                w_each = 1.0 / len(defensive)
                return {s: w_each for s in defensive}
            return {aid: 0.0 for aid in ctx.prices}
        weights = {sym: 1.0 / len(keep) for sym in keep}

        # volatility targeting: scale risky exposure when realized vol is hot
        vol_target = self.params.get("vol_target", 0.0) or 0.0
        vol_lb = int(self.params.get("vol_lookback", 20))
        if vol_target > 0 and any(w > 0 for w in weights.values()):
            port_rets = self._portfolio_realized_returns(ctx, date, weights, vol_lb)
            if len(port_rets) >= 10:
                mean = sum(port_rets) / len(port_rets)
                var = sum((r - mean) ** 2 for r in port_rets) / max(1, len(port_rets) - 1)
                realized = (var ** 0.5) * (252 ** 0.5)
                if realized > vol_target > 0:
                    scale = min(1.0, vol_target / realized)
                    weights = {s: w * scale for s, w in weights.items()}
        return weights

    def _portfolio_realized_returns(
        self, ctx: StrategyContext, date: str, weights: dict[str, float], lb: int
    ) -> list[float]:
        """Realized daily portfolio returns over the last lb days under given weights."""
        active = {s: w for s, w in weights.items() if w > 0}
        if not active:
            return []
        common: list[str] | None = None
        rets_by_sym: dict[str, dict[str, float]] = {}
        for sym in active:
            series = ctx.prices.get(sym, {})
            dates = sorted(d for d in series.keys() if d <= date)[- (lb + 1):]
            rets_by_sym[sym] = {
                d2: series[d2] / series[d1] - 1.0
                for d1, d2 in zip(dates, dates[1:])
                if series.get(d1, 0) > 0
            }
            ds = set(rets_by_sym[sym].keys())
            common = ds if common is None else (common & ds)
        if not common:
            return []
        days = sorted(common)
        total_w = sum(active.values()) or 1.0
        return [
            sum(active[s] / total_w * rets_by_sym[s][d] for s in active)
            for d in days
        ]



BUILTIN_STRATEGIES = [
    EqualWeightStrategy,
    VolatilityInverseStrategy,
    MomentumRotationStrategy,
    RiskParityStrategy,
    SMATimingStrategy,
    AssetRotationStrategy,
]
