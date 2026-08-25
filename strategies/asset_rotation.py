"""name: 大类资产动量轮动
description: 月度按过去 N 个交易日涨幅选最强 K 个大类资产等权持有
rebalance_freq: monthly
version_note: 1.0.0
factor_keys: 
---

大类资产动量轮动策略 — 在黄金/绝对收益/A股/债券/海外等大类之间做动量轮动。

策略逻辑：
  1. 从 universe 中按 symbol 白名单（params.symbols）筛出候选大类
  2. 每月末计算每个候选过去 lookback_days 个交易日的动量（价格涨跌幅）
  3. 买入动量最强的前 top_k 个标的并等权配置，其余空仓现金
  4. 候选不足或价格不足时维持现状（返回 None）

参数（params.schema）：
  - symbols: 逗号分隔的大类标的 symbol 白名单，默认
    000217(黄金),000667(绝对收益),002910(A股),006432(债券),378546(海外)
  - lookback_days: 动量窗口（交易日），默认 180
  - top_k: 持有最强前几个等权，默认 3

实测（2021-09~2026-08，含真实费率：C 类销售服务费/各标的赎回档位/T+N 到账）：
  lookback=180, top_k=1 → 年化 27.69%, 夏普 1.167, 最大回撤 -35.5%
  lookback=180, top_k=2 → 年化 16.30%, 夏普 0.980, 最大回撤 -13.9%
  lookback=180, top_k=3 → 年化 16.08%, 夏普 1.146, 最大回撤 -15.6%  ← 默认(均衡)
"""

from finkit_strategy import Strategy, StrategyContext


class AssetRotationStrategy(Strategy):
    """月度动量轮动：选最强前 K 个大类等权持有。"""

    name = "大类资产动量轮动"
    rebalance_freq = "monthly"
    params_schema = {
        "symbols": {"type": "str", "default": "000217,000667,002910,006432,378546"},
        "lookback_days": {"type": "int", "default": 180, "min": 20, "max": 500},
        "top_k": {"type": "int", "default": 3, "min": 1, "max": 6},
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

        top = sorted(momentum, key=momentum.get, reverse=True)[: self.params["top_k"]]
        w = 1.0 / len(top)
        return {sym: w for sym in top}