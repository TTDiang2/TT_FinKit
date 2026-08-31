"""ORM for research_asset_stats — 预计算指标表（见 services/asset_stats.py）。"""
from sqlalchemy import Column, Float, Integer, String, Text

from ..database import Base


class ResearchAssetStats(Base):
    __tablename__ = "research_asset_stats"

    asset_id = Column(String, primary_key=True)
    symbol = Column(String)
    name = Column(String)
    status = Column(String)
    rows = Column(Integer)
    last_date = Column(String)
    ret_21d = Column(Float)
    ret_63d = Column(Float)
    ret_252d = Column(Float)
    ann_1y = Column(Float)
    vol_1y = Column(Float)
    sharpe_1y = Column(Float)
    mdd_1y = Column(Float)
    ann_all = Column(Float)
    vol_all = Column(Float)
    sharpe_all = Column(Float)
    mdd_all = Column(Float)
    computed_at = Column(Text)
