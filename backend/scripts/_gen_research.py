"""Generate strategies/research/research_aw.py from all_weather.py with
additional OPTIONAL research features (all default-off so base behavior
matches the delivered engine):

  pull_boost      IDEA-01  ON-regime pullback → risky budget ×(1+pull_boost)
  corr_cap        IDEA-04  risk picks: skip candidate correlated > cap with a pick
  r2mom           IDEA-05  risk score mode "r2mom": 252d log-price R² × total return
  rate_tilt       IDEA-06  us_rate 20d slope gate on gold budget
  gold_hysteresis IDEA-08  gold ON until mom252 < gold_floor_off (hysteresis band)

Run once from backend/: python scripts/_gen_research.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "strategies" / "all_weather.py"
OUT = ROOT / "strategies" / "research" / "research_aw.py"
code = SRC.read_text(encoding="utf-8")

# strip module docstring, add research docstring
body = code.split('"""', 2)[2]

# --- new params appended into params_schema ---
body = body.replace('''        "scale_hysteresis": {"type": "float", "default": 0.12, "min": 0.0, "max": 0.5},
    }''',
'''        "scale_hysteresis": {"type": "float", "default": 0.12, "min": 0.0, "max": 0.5},
        # ---- research features（默认关闭 = 与交付引擎一致）----
        "pull_boost": {"type": "float", "default": 0.0, "min": 0.0, "max": 1.0},
        "pull_window": {"type": "int", "default": 63, "min": 10, "max": 250},
        "corr_cap": {"type": "float", "default": 0.0, "min": 0.0, "max": 1.0},
        "corr_lookback": {"type": "int", "default": 126, "min": 20, "max": 500},
        "rate_tilt": {"type": "float", "default": 0.0, "min": 0.0, "max": 1.0},
        "rate_window": {"type": "int", "default": 20, "min": 5, "max": 120},
        "gold_floor_off": {"type": "float", "default": -0.02, "min": -0.5, "max": 0.5},
    }''')

# --- gold hysteresis + rate tilt inside target_weights gold block ---
body = body.replace('''        # 黄金桶
        gold_budget = float(self.params.get("gold_budget", 0.0))
        gold_sym, gold_m = self._gold_pick(ctx, date)
        if gold_sym is not None and gold_m is not None \\
                and gold_m > float(self.params.get("gold_floor", -0.02)) and gold_budget > 0:
            weights[gold_sym] = weights.get(gold_sym, 0.0) + gold_budget''',
'''        # 黄金桶（可选迟滞带：已开仓后跌穿 gold_floor_off 才平，减少 ON/OFF 抖动）
        gold_budget = float(self.params.get("gold_budget", 0.0))
        gold_sym, gold_m = self._gold_pick(ctx, date)
        gold_on = False
        if gold_sym is not None and gold_m is not None:
            if gold_sym in (ctx.current_weights or {}):
                gold_on = gold_m > float(self.params.get("gold_floor_off", -0.02))
            else:
                gold_on = gold_m > float(self.params.get("gold_floor", -0.02))
        if gold_on and gold_budget > 0:
            # IDEA-06 宏观利率斜率：美债利率快速上行是黄金逆风（可选）
            tilt = float(self.params.get("rate_tilt", 0.0) or 0.0)
            if tilt > 0:
                slope = self._rate_slope(ctx, date, "us_rate")
                if slope is not None and slope > 0:
                    gold_budget *= max(0.0, 1.0 - tilt)
            weights[gold_sym] = weights.get(gold_sym, 0.0) + gold_budget''')

# --- pullback boost: scale risky up in ON-regime pullback (before vol response) ---
body = body.replace('''        # 波动率响应：风险+黄金组合近端波动超目标 → 按比例把预算挪去防守桶。''',
'''        # 波动率响应：风险+黄金组合近端波动超目标 → 按比例把预算挪去防守桶。''')

# --- correlation cap in _risk_picks ---
body = body.replace('''        ranked = sorted(scores, key=scores.get, reverse=True)
        picked = [s for s in ranked[:k] if moms.get(s, -9.9) > floor]''',
'''        ranked = sorted(scores, key=scores.get, reverse=True)
        cap = float(self.params.get("corr_cap", 0.0) or 0.0)
        if cap > 0:
            picked: list[str] = []
            for s in ranked:
                if len(picked) >= k:
                    break
                if moms.get(s, -9.9) <= floor:
                    continue
                if any(self._corr(ctx, date, s, p) > cap for p in picked):
                    continue
                picked.append(s)
        else:
            picked = [s for s in ranked[:k] if moms.get(s, -9.9) > floor]''')

# --- r2mom score mode ---
body = body.replace('''            moms[sym] = m
            vol = self._ann_vol(series, date, 126)
            scores[sym] = m if score_mode == "raw" else m / max(vol, VOL_FLOOR)''',
'''            moms[sym] = m
            vol = self._ann_vol(series, date, 126)
            if score_mode == "raw":
                scores[sym] = m
            elif score_mode == "r2mom":
                scores[sym] = m * self._trend_r2(series, date, gw)
            else:
                scores[sym] = m / max(vol, VOL_FLOOR)''')

# --- new helper methods ---
body = body.replace('''    def _sym_names(self, ctx: StrategyContext) -> dict[str, str]:''',
'''    def _sleeve_momentum(
        self, ctx: StrategyContext, date: str, weights: dict[str, float], window: int
    ) -> float | None:
        """给定权重组合最近 window 日的累计收益（判断趋势内回调）。"""
        total_w = sum(weights.values()) or 1.0
        nav = 1.0
        n = 0
        by_day: dict[str, list[float]] = {}
        for sym in weights:
            series = ctx.prices.get(sym, {})
            dates = sorted(d for d in series.keys() if d <= date)[-(window + 1):]
            for d1, d2 in zip(dates, dates[1:]):
                if series.get(d1, 0) > 0:
                    by_day.setdefault(d2, []).append(series[d2] / series[d1] - 1.0)
        days = sorted(by_day)[-window:]
        for d in days:
            rs = by_day.get(d, [])
            if rs:
                nav *= (1.0 + sum(rs) / len(rs))
                n += 1
        if n < max(10, window // 3):
            return None
        return nav - 1.0

    def _corr(self, ctx: StrategyContext, date: str, s1: str, s2: str,
              lb: int | None = None) -> float:
        """两标的最近 lb 日的日收益相关系数（缺数据返回 1.0=视为高相关）。"""
        lb = int(lb or self.params.get("corr_lookback", 126))

        def rets(sym: str) -> dict[str, float]:
            series = ctx.prices.get(sym, {})
            dates = sorted(d for d in series.keys() if d <= date)[-(lb + 1):]
            return {d2: series[d2] / series[d1] - 1.0
                    for d1, d2 in zip(dates, dates[1:]) if series.get(d1, 0) > 0}

        r1, r2 = rets(s1), rets(s2)
        common = sorted(set(r1) & set(r2))
        if len(common) < 30:
            return 1.0
        xs = [r1[d] for d in common]
        ys = [r2[d] for d in common]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        vx = sum((a - mx) ** 2 for a in xs) ** 0.5
        vy = sum((b - my) ** 2 for b in ys) ** 0.5
        if vx <= 0 or vy <= 0:
            return 1.0
        return cov / (vx * vy)

    def _trend_r2(self, series: dict[str, float], date: str, window: int) -> float:
        """log 价格对时间回归的 R²（趋势平滑度 0~1）。"""
        import math as _m
        dates = sorted(d for d in series.keys() if d <= date)[-(window + 1):]
        pts = [(i, _m.log(series[d])) for i, d in enumerate(dates) if series.get(d, 0) > 0]
        if len(pts) < 40:
            return 0.0
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        syy = sum((p[1] - my) ** 2 for p in pts)
        if sxx <= 0 or syy <= 0:
            return 0.0
        return (sxy * sxy) / (sxx * syy)

    def _rate_slope(self, ctx: StrategyContext, date: str, factor_key: str) -> float | None:
        """factor_values 中利率因子的近 rate_window 日斜率。"""
        fv = getattr(ctx, "factor_values", {}) or {}
        ser = fv.get(factor_key) or {}
        dates = sorted(d for d in ser.keys() if d <= date)
        w = int(self.params.get("rate_window", 20))
        if len(dates) <= w:
            return None
        return float(ser[dates[-1]]) - float(ser[dates[-1 - w]])

    def _sym_names(self, ctx: StrategyContext) -> dict[str, str]:''')

# docstring
head = '''"""name: 研究引擎-多资产趋势
description: [研究用] all_weather 引擎 + 回调加仓/反抱团/R2动量/利率斜率/黄金迟滞 可选特性
rebalance_freq: monthly
version_note: 0.1.0-research
factor_keys: us_rate,cn_rate,gold,equity,bond
---

[研究用文件] 与《全天候策略》同引擎，追加 5 个默认关闭的研究特性（IDEA-01/04/05/06/08）。
特性说明见 backend/scripts/_gen_research.py 与 docs/STRATEGY_PLAYBOOK.md §6。
默认参数 = 交付引擎基线；只有显式传参才启用特性。
"""

from finkit_strategy import Strategy, StrategyContext


GOLD_CANDIDATES = ["000217", "002611", "002963", "004253"]
DEFENSIVE_WHITELIST = ["015991", "003377", "000188", "019203", "000420", "002175"]
SUSPENDED = ["005676", "027784"]  # 暂停申购，实盘买不进
VOL_FLOOR = 0.05


'''

body = body.replace("""        # 防守桶承接剩余""",
"""        # IDEA-01 回调加仓（在波动率响应**之后**执行才有意义：
        # 趋势内回调是统计上最佳的加仓窗，允许当月突破波动目标）：
        # sleeve 近 pull_window 日动量 < 0 → 风险桶 ×(1+pull_boost)，从防守桶按比例挪。
        pb = float(self.params.get("pull_boost", 0.0) or 0.0)
        if pb > 0:
            def_set_pb = set(self._defensive_syms(ctx, date))
            risky_pb = {s: w for s, w in weights.items() if s not in def_set_pb}
            if risky_pb and sum(risky_pb.values()) > 1e-6:
                pw = int(self.params.get("pull_window", 63))
                sleeve_mom = self._sleeve_momentum(ctx, date, risky_pb, pw)
                if sleeve_mom is not None and sleeve_mom < 0:
                    r_total = sum(risky_pb.values())
                    d_total = sum(w for s, w in weights.items() if s in def_set_pb)
                    reallocate = min(r_total * pb, d_total)
                    if reallocate > 1e-9:
                        r_scale = (r_total + reallocate) / r_total
                        d_scale = (d_total - reallocate) / d_total if d_total > 0 else 1.0
                        weights = {
                            s: (w * r_scale if s in risky_pb else w * d_scale)
                            for s, w in weights.items()
                        }

        # 防守桶承接剩余""", 1)

body = body.replace('class AllWeatherStrategy(Strategy):', 'class ResearchAWStrategy(Strategy):')
body = body.replace('name = "全天候策略"', 'name = "研究引擎-多资产趋势"')
body = body.replace('"""金/风险年线动量闸门 + 债券防守核 + 波动率响应预算的全天候配置。"""',
                    '"""[研究用] 多资产趋势引擎 + 可选研究特性。"""')

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(head + body, encoding="utf-8")
import ast
ast.parse(OUT.read_text(encoding="utf-8"))
print("wrote", OUT)
