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


class AssetRotationStrategy(Strategy):
    """大类资产动量轮动：月度按过去 N 个交易日涨幅选最强 K 个等权持有。

    从 universe 中按 symbol 白名单筛出候选大类（如黄金/绝对收益/A股/债券/海外），
    每月末计算各候选过去 lookback_days 个交易日的动量（价格涨跌幅），
    买入动量最强的 top_k 个标的并等权配置。若候选不足或价格不足则维持现状。
    """
    name = "大类资产动量轮动"
    description = "月度选最强 K 个等权持有；缓冲带减少换手；绝对动量过滤震荡市"
    rebalance_freq = "monthly"
    params_schema = {
        "symbols": {"type": "str", "default": "000217,000667,002910,006432,378546"},
        "lookback_days": {"type": "int", "default": 180, "min": 20, "max": 500},
        "top_k": {"type": "int", "default": 3, "min": 1, "max": 6},
        "buffer": {"type": "int", "default": 1, "min": 0, "max": 3},
        "momentum_floor": {"type": "float", "default": 0.0, "min": -1.0, "max": 0.5},
    }

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        # 从池中筛出白名单里真实存在的大类标的（symbol 键）
        pool_symbols = {a["symbol"] for a in ctx.pool}
        symbols = [
            s.strip() for s in self.params["symbols"].split(",") if s.strip()
        ]
        candidates = [s for s in symbols if s in pool_symbols]
        if not candidates:
            return None

        lookback = self.params["lookback_days"]
        momentum: dict[str, float] = {}
        for sym in candidates:
            series = ctx.prices.get(sym, {})
            dates = sorted(d for d in series.keys() if d <= date)
            if len(dates) < 2:
                continue
            # 取 date 前最近 lookback 个交易日：起点 = 窗口最旧价，终点 = 最新价
            window = dates[-(lookback + 1):] if len(dates) > lookback else dates
            base = series[window[0]]
            latest = series[window[-1]]
            if base and base > 0:
                momentum[sym] = latest / base - 1.0
        if not momentum:
            return None

        ranked_all = sorted(momentum, key=momentum.get, reverse=True)
        # 绝对动量过滤：动量低于 floor 的资产不入选；
        # 全部低于 floor 时返回全零 target（空仓避险），避免震荡市硬扛
        floor = self.params.get("momentum_floor", 0.0)
        ranked = [s for s in ranked_all if momentum[s] >= floor]
        if not ranked:
            return {aid: 0.0 for aid in ctx.prices}
        rank = {sym: i for i, sym in enumerate(ranked)}
        k = self.params["top_k"]
        buffer_n = self.params.get("buffer", 0)

        # 缓冲带：top_k 直接入选；已持有且仍在 top_(k+buffer) 内的保留，
        # 避免排名边缘反复进出（降低换手与 T+N 摩擦成本）
        keep = set(ranked[:k])
        for sym, w in (ctx.current_weights or {}).items():
            if w > 1e-6 and sym in rank and rank[sym] < k + buffer_n:
                keep.add(sym)
        if not keep:
            return {aid: 0.0 for aid in ctx.prices}
        w_each = 1.0 / len(keep)
        return {sym: w_each for sym in keep}


BUILTIN_STRATEGIES = [
    EqualWeightStrategy,
    VolatilityInverseStrategy,
    MomentumRotationStrategy,
    RiskParityStrategy,
    SMATimingStrategy,
    AssetRotationStrategy,
]
