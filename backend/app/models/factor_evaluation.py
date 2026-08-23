"""Factor evaluation models — IC/ICIR test results per factor.

``FactorIcPoint``: one row per (factor, month-end) — cross-sectional IC of the
factor's fund-pool exposures vs next-month fund returns.

``FactorEvaluation``: one aggregated row per factor (upserted on recompute) —
ICIR / t-stat / win rate / IC decay / quantile returns / long-short metrics /
screening result against configurable thresholds.
"""
from sqlalchemy import Column, String, Float, Integer, Text, UniqueConstraint
from datetime import datetime
import uuid

from ..database import Base


class FactorIcPoint(Base):
    __tablename__ = "factor_ic_points"
    __table_args__ = (UniqueConstraint("user_id", "factor_key", "date", name="uq_factor_ic_point"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    factor_key = Column(String, nullable=False, index=True)   # links to factors.key
    date = Column(String, nullable=False)                     # month-end as_of YYYY-MM-DD
    ic = Column(Float, nullable=True)                         # Pearson
    rank_ic = Column(Float, nullable=True)                    # Spearman
    n = Column(Integer, nullable=True)                        # cross-section size (fund count)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class FactorEvaluation(Base):
    __tablename__ = "factor_evaluations"
    __table_args__ = (UniqueConstraint("user_id", "factor_key", name="uq_factor_evaluation"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    factor_key = Column(String, nullable=False, index=True)
    window_start = Column(String, nullable=True)
    window_end = Column(String, nullable=True)
    n_periods = Column(Integer, nullable=True)

    # IC aggregates (None when n_periods < 6 — not statistically meaningful)
    ic_mean = Column(Float, nullable=True)
    ic_std = Column(Float, nullable=True)
    rank_ic_mean = Column(Float, nullable=True)
    icir = Column(Float, nullable=True)                       # mean(IC)/std(IC), per-period
    icir_annualized = Column(Float, nullable=True)            # icir * sqrt(12)
    t_stat = Column(Float, nullable=True)                     # icir * sqrt(N)
    win_rate = Column(Float, nullable=True)                   # mean(IC > 0)
    ic_autocorr_lag1 = Column(Float, nullable=True)
    ic_decay_1 = Column(Float, nullable=True)                 # mean RankIC vs t+1 return
    ic_decay_2 = Column(Float, nullable=True)                 # vs t+2
    ic_decay_3 = Column(Float, nullable=True)                 # vs t+3

    # Quantile portfolio (5 groups by exposure, equal weight, monthly rebalance)
    quantile_returns = Column(Text, nullable=True)            # JSON {"q1":..,"q5":..,"spread":..}

    # Long-short portfolio (Q5 long, Q1 short)
    ls_nav = Column(Text, nullable=True)                      # JSON [{date, nav}]
    ls_ann_return = Column(Float, nullable=True)
    ls_vol = Column(Float, nullable=True)
    ls_sharpe = Column(Float, nullable=True)
    ls_max_dd = Column(Float, nullable=True)
    ls_calmar = Column(Float, nullable=True)
    ls_alpha = Column(Float, nullable=True)                   # vs pool equal-weight benchmark, annualized
    ls_beta = Column(Float, nullable=True)
    ls_ir = Column(Float, nullable=True)                      # ann excess return / ann tracking error

    # Screening vs thresholds ({"rank_ic_mean": true, ...})
    screen_result = Column(Text, nullable=True)
    computed_at = Column(String, default=lambda: datetime.utcnow().isoformat())
