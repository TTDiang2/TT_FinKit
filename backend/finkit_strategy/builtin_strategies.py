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


BUILTIN_STRATEGIES = [
    EqualWeightStrategy,
    VolatilityInverseStrategy,
    MomentumRotationStrategy,
    RiskParityStrategy,
    SMATimingStrategy,
]
