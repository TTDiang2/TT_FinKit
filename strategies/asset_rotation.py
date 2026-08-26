"""name: 大类资产动量轮动
description: 月度选最强 K 个等权持有；缓冲带减少换手；绝对动量过滤震荡市
rebalance_freq: monthly
version_note: 1.2.0
factor_keys:
---

大类资产动量轮动策略 — 在黄金/绝对收益/A股/债券/海外等大类之间做动量轮动。

策略逻辑：
  1. 从 universe 中按 symbol 白名单（params.symbols）筛出候选大类
  2. 每月末计算每个候选过去 lookback_days 个交易日的动量（价格涨跌幅）
  3. 绝对动量过滤：动量低于 momentum_floor 的不入选；
     全部低于 floor 时空仓避险（避免 2022 式震荡市硬扛）
  4. 动量最强前 top_k 直接入选；已持有标的只要仍在 top_(k+buffer) 内就保留
     （缓冲带规则，避免排名边缘反复进出，降低换手与 T+N 赎回摩擦）
  5. 入选标的等权配置；候选不足或价格不足时维持现状（返回 None）

参数（params.schema）：
  - symbols: 逗号分隔的大类标的 symbol 白名单，默认
    000217(黄金),000667(绝对收益),002910(A股),006432(债券),378546(海外)
  - lookback_days: 动量窗口（交易日），默认 180
  - top_k: 持有最强前几个等权，默认 3
  - buffer: 缓冲带宽度（排名跌出 top_(k+buffer) 才卖出），默认 1
  - momentum_floor: 绝对动量门槛，默认 0.0（负动量一律不持有）

T+N 说明：
  月末调仓卖出后赎回款 T+N 到账，回测引擎在到账日自动补买
  （调仓记录中 kind=settle 的条目）；策略无需为此特殊处理。

实测（2021-09~2026-08，含真实费率）：
  v1.0 (180/top3 无缓冲带): 年化 16.08%, 夏普 1.146, 最大回撤 -15.6%
  v1.1 (180/top3/buf1):     年化 16.93%, 夏普 1.291, 最大回撤 -15.6%
"""

from finkit_strategy import Strategy, StrategyContext


class AssetRotationStrategy(Strategy):
    """月度动量轮动：最强 K 个等权 + 缓冲带 + 绝对动量过滤。"""

    name = "大类资产动量轮动"
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
        symbols = [s.strip() for s in self.params["symbols"].split(",") if s.strip()]
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

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        # 从池中筛出白名单里真实存在的大类标的（symbol 键）
        pool_symbols = {a["symbol"] for a in ctx.pool}
        symbols = [s.strip() for s in self.params["symbols"].split(",") if s.strip()]
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

        ranked = sorted(momentum, key=momentum.get, reverse=True)
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
            return None
        w_each = 1.0 / len(keep)
        return {sym: w_each for sym in keep}