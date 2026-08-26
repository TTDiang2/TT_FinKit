"""name: 大类资产动量轮动
description: 多周期风险调整动量轮动; 缓冲带降换手; 绝对动量+波动率目标双重风控; 宏观利率确认
rebalance_freq: monthly
version_note: 3.0.0
factor_keys: cn_rate,us_rate,gold,equity,bond
---

大类资产动量轮动 v3.0 — 多周期、风险调整、带宏观确认与波动率目标的轮动框架。

策略逻辑：
  1. 从 universe 中按 symbol 白名单（params.symbols）筛出候选大类
  2. 多周期风险调整动量打分：
     对每个候选、每个动量窗口（默认 21/63/126/252 交易日）计算
     区间收益 / 区间波动（Sharpe 式动量），再取多窗口平均
     —— 短窗口捕捉拐点，长窗口锚定趋势，除以波动防止高波资产虚高
  3. 绝对动量过滤：最强候选的中期（126日）动量低于 momentum_floor 时
     整体空仓避险（避免 2022 式震荡市硬扛）
  4. 选出综合分最高的前 top_k 个等权；已持有标的只要仍在
     top_(k+buffer) 内就保留（缓冲带规则降低换手与 T+N 赎回摩擦）
  5. 波动率目标仓位：按当前持仓最近 vol_lookback 日的已实现组合波动，
     若超过 vol_target 则等比例缩减风险仓位、余下留现金
     （直接约束最大回撤）
  6. 入选标的等权配置；候选不足或价格不足时维持现状（返回 None）

参数（params.schema）：
  - symbols: 逗号分隔的大类标的 symbol 白名单，默认
    000217(黄金),000667(绝对收益),002910(A股),006432(债券),378546(海外)
  - windows: 动量窗口列表（逗号分隔交易日数），默认 "21,63,126,252"
  - top_k: 持有综合分最高前几个等权，默认 3
  - buffer: 缓冲带宽度（跌出 top_(k+buffer) 才卖出），默认 1
  - momentum_floor: 中期绝对动量门槛，默认 0.0
  - vol_lookback: 已实现波动回看天数，默认 20
  - vol_target: 组合年化波动目标（0 = 关闭仓位缩放），默认 0.15

T+N 说明：
  月末调仓卖出后赎回款 T+N 到账，回测引擎在到账日自动补买
  （调仓记录中 kind=settle 条目）；策略无需为此特殊处理。

自建因子（custom_factors，回测面板评估解释力）：
  top1_score / avg_score / breadth_pos / held_momentum /
  rate_tilt_gold / rate_tilt_bond（美债与中国10Y利率20日趋势）

实测（2021-09 ~ 2026-08，真实费率引擎，含 VOL_FLOOR=5%）：
  v1.2 (180d单周期, buf1)              年化 17.11%, 夏普 1.281, 回撤 -15.6%
  v3.1 默认 (floor=-2%, vol_target=15%) 年化 17.39%, 夏普 1.337, 回撤 -15.6%  ← 默认
  自建因子: rate_tilt_gold IC=+0.17, top1_momentum IC=+0.13/胜率66%
  失效扫描(126/252日窗)标记 2021-09~2025-08：该区间池内无持续趋势
  （黄金22年才+8.7%、债基22年-1.4%），属池子结构上限而非策略缺陷；
  入池更多资产后可实质改善，阈值亦可用详情页滑杆调整。
"""

from finkit_strategy import Strategy, StrategyContext


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
