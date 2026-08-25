"""name: 黄金双均线择时
description: 快线上穿慢线全仓持有，下穿空仓转现金；可选黄金因子暴露确认
rebalance_freq: monthly
version_note: 2.0.0
factor_keys: gold
---

黄金双均线择时策略（示例）— 用于 000217 华安黄金ETF联接C。

策略逻辑：
  1. 计算快/慢两条均线（fast_ma / slow_ma，默认 20/60 日）
  2. 快线上穿慢线（金叉）→ 全仓持有 000217
  3. 快线下穿慢线（死叉）→ 空仓（权重 0，转现金）
  4. （可选）黄金因子确认：金叉时若 ctx.factor_exposure 显示 000217 对黄金因子
     暴露过低，则放弃买入 —— 展示如何调取因子数据

导入方式：
  「投资 → 策略 → 导入策略 (.py)」选择本文件，或
  POST /api/strategies/import {"name":"黄金双均线择时","code":"<本文件内容>"}

v2.0.0: 迁移到 base.Strategy 官方接口 target_weights(ctx, date)，
        废弃旧接口 generate_target_weights(ctx)（v1 无法被引擎执行）。
"""

from finkit_strategy import Strategy, StrategyContext


class GoldDualMA(Strategy):
    """快慢均线金叉/死叉择时黄金基金。"""

    name = "黄金双均线择时"
    rebalance_freq = "monthly"
    params_schema = {
        "fast_ma": {"type": "int", "default": 20, "description": "快均线天数"},
        "slow_ma": {"type": "int", "default": 60, "description": "慢均线天数"},
        "use_factor_confirm": {"type": "bool", "default": False, "description": "是否用黄金因子暴露确认"},
    }

    def target_weights(self, ctx: StrategyContext, date: str) -> dict[str, float] | None:
        fast = self.params.get("fast_ma", 20)
        slow = self.params.get("slow_ma", 60)

        prices = ctx.prices  # symbol -> {date: close}
        syms = self.universe(ctx)  # list of symbols in pool
        if not syms:
            return None
        sym = syms[0]
        if sym not in prices:
            return None

        closes = sorted(prices[sym].items())  # [(date, close), ...]
        if len(closes) < slow:
            return {sym: 0.0}

        fast_ma = sum(c for _, c in closes[-fast:]) / fast
        slow_ma = sum(c for _, c in closes[-slow:]) / slow

        # 金叉 → 全仓；死叉 → 空仓
        target = 1.0 if fast_ma > slow_ma else 0.0

        # （可选）因子暴露确认
        if target > 0 and self.params.get("use_factor_confirm"):
            gold_beta = ctx.factor_exposure(sym, "gold")
            if gold_beta < 0.3:
                # 黄金暴露太低，放弃买入
                target = 0.0

        return {sym: target}
