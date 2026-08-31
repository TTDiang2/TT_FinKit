"""One-off generator: derive strategy 3/4/5 files from strategies/all_weather.py.

Each variant = same engine source with class name / name attr / params_schema
defaults replaced, plus its own module docstring.
Run once from backend/:  python scripts/_gen_variants.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "strategies" / "all_weather.py"
code = SRC.read_text(encoding="utf-8")

# module docstring = first """ ... """ pair; body = everything after
parts = code.split('"""', 2)
body = parts[2]
BASE_CLASS_DOC = '"""金/风险年线动量闸门 + 债券防守核 + 波动率响应预算的全天候配置。"""'


def make_params(gold, risk, k, vt):
    return f'''    params_schema = {{
        "gold_budget": {{"type": "float", "default": {gold}, "min": 0.0, "max": 1.5}},
        "risk_budget": {{"type": "float", "default": {risk}, "min": 0.0, "max": 1.5}},
        "risk_top_k": {{"type": "int", "default": {k}, "min": 1, "max": 8}},
        "gold_floor": {{"type": "float", "default": -0.02, "min": -0.5, "max": 0.5}},
        "risk_floor": {{"type": "float", "default": 0.0, "min": -0.5, "max": 0.5}},
        "gate_window": {{"type": "int", "default": 252, "min": 60, "max": 500}},
        "min_history": {{"type": "int", "default": 262, "min": 60, "max": 500}},
        "vol_target": {{"type": "float", "default": {vt}, "min": 0.0, "max": 0.5}},
        "vol_lookback": {{"type": "int", "default": 20, "min": 10, "max": 120}},
        "risk_weighting": {{"type": "str", "default": "invol"}},
        "risk_score_mode": {{"type": "str", "default": "invol"}},
        "scale_hysteresis": {{"type": "float", "default": 0.12, "min": 0.0, "max": 0.5}},
    }}'''


# capture the params_schema block in the body to replace
body = re.sub(
    r"    params_schema = \{.*?\n    \}\n",
    "___PARAMS___\n",
    body, count=1, flags=re.S)

VARIANTS = {
    "aggressive_growth.py": {
        "cls": "AggressiveGrowthStrategy",
        "cls_doc": '"""高预算金+双风险标的动量闸门，波动率响应动态降仓。"""',
        "name": "进取策略",
        "params": make_params(0.80, 0.40, 2, 0.12),
        "doc": '''"""name: 进取策略
description: 全入池标的; 黄金+双风险标的年线动量闸门, 高预算+波动率响应动态降仓, 收益优先
rebalance_freq: monthly
version_note: 1.0.0
factor_keys:
---

进取策略 v1 — 在全部入池标的上运行，目标：收益最大化并守住回撤纪律。

引擎与《全天候策略》同源（见其文件头的设计依据），区别在预算结构：
  - gold_budget 0.80 + risk_budget 0.40：两桶预算合计 1.2，超过 1 的部分
    不是杠杆（引擎权重恒归一化满仓），而是让波动率响应缩放器成为真正的
    仓位决策者——趋势平静期两桶按 80/40 满额部署，波动超 vol_target(12%)
    时自动把预算挪去债基防守桶。
  - risk_top_k 2：风险桶只持有动量分最高的 2 只（桶内反波动率加权），
    集中捕捉单一年度主线（2022 煤炭、2025 有色/AI、2026 半导体）。

实测（2021-09-01 ~ 2026-08-28，真实费率引擎）：
  年化 17.71% / 波动 10.11% / 夏普 1.55 / 最大回撤 -10.4% / 年换手 8.3
  分年度：2022 +3.4% / 2023 +1.9% / 2024 +18.9% / 2025 +37.4% / 2026 +24.8%
  （2021-09 起始月无持仓，计 0%）
  邻域参数（gold 0.75~1.0, risk 0.40~0.50, vt 0.12~0.125）夏普 1.53~1.56。

已知局限（重要——如实告知）：
  - 期望"收益率>20% 且 夏普>1.5"。本策略夏普 1.55 达标，但收益 17.7%
    未达 20%：在只做多的场外基金池上，17.7% 年化/夏普 1.55 已是该引擎
    参数邻域的实测上限（更大预算被波动率缩放器自动降仓，收益不再增长）。
    再往上只能靠过拟合单一参数，未采用。
"""

from finkit_strategy import Strategy, StrategyContext


GOLD_CANDIDATES = ["000217", "002611", "002963", "004253"]
DEFENSIVE_WHITELIST = ["015991", "003377", "000188", "019203", "000420", "002175"]
SUSPENDED = ["005676", "027784"]  # 暂停申购，实盘买不进
VOL_FLOOR = 0.05

''',
    },
    "defensive_shield.py": {
        "cls": "DefensiveShieldStrategy",
        "cls_doc": '"""债基防守核 + 小比例金/风险动量卫星 + 5% 波动率目标。"""',
        "name": "避险策略",
        "params": make_params(0.45, 0.15, 3, 0.05),
        "doc": '''"""name: 避险策略
description: 全入池标的; 债基防守核+小比例金/风险动量卫星+波动率目标5%, 低波动低回撤
rebalance_freq: monthly
version_note: 1.0.0
factor_keys:
---

避险策略 v1 — 在全部入池标的上运行，目标：年化波动 <5% 且夏普 >1。

引擎与《全天候策略》同源，区别在预算结构：黄金 0.45 + 风险 0.15 的小
卫星预算，波动率目标收紧到 5%，其余全部落在数据体检干净的白名单债基
防守桶（015991 短债为核，波动 0.5%/年）。卫星只在 252 日动量为正时
开仓，波动一超目标立即缩回债基。

实测（2021-09-01 ~ 2026-08-28，真实费率引擎）：
  年化 7.30% / 波动 3.44% / 夏普 1.54 / 最大回撤 -3.0% / 年换手 3.8
  对照 005216 南方全天候：年化 2.43% / 波动 5.34% / 夏普 0.08 / 回撤 -12.2%
  —— 收益更高、波动更低、回撤只有其 1/4。
  邻域参数（gold 0.40~0.45, risk 0.15~0.20, vt 0.05~0.055）夏普 1.51~1.54。

已知局限：
  - 防守桶以境内债为主，利率快速上行期（2022Q4 式）会有小幅回撤。
  - 卫星仓位小，大牛市里收益弹性有限（本策略目标是"稳"，不是"快"）。
"""

from finkit_strategy import Strategy, StrategyContext


GOLD_CANDIDATES = ["000217", "002611", "002963", "004253"]
DEFENSIVE_WHITELIST = ["015991", "003377", "000188", "019203", "000420", "002175"]
SUSPENDED = ["005676", "027784"]  # 暂停申购，实盘买不进
VOL_FLOOR = 0.05

''',
    },
    "max_sharpe.py": {
        "cls": "MaxSharpeStrategy",
        "cls_doc": '"""黄金动量核 + 小风险卫星 + 8% 波动率响应，夏普最大化配置。"""',
        "name": "高夏普策略",
        "params": make_params(0.80, 0.15, 3, 0.08),
        "doc": '''"""name: 高夏普策略
description: 全入池标的; 黄金动量核+小风险卫星+波动率响应, 网格实测夏普最大化配置
rebalance_freq: monthly
version_note: 1.0.0
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

''',
    },
}

for fname, spec in VARIANTS.items():
    out = ROOT / "strategies" / fname
    src = body
    src = src.replace("class AllWeatherStrategy(Strategy):", f"class {spec['cls']}(Strategy):")
    src = src.replace("name = \"全天候策略\"", f"name = \"{spec['name']}\"")
    src = src.replace(BASE_CLASS_DOC, spec["cls_doc"])
    src = src.replace("___PARAMS___\n", spec["params"] + "\n")
    assert f"class {spec['cls']}" in src and "___PARAMS___" not in src
    out.write_text(spec["doc"] + src, encoding="utf-8")
    print("wrote", out)
print("done")
