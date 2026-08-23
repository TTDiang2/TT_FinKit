from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime
from ..database import Base


class ResearchAssetHolding(Base):
    """Cached holdings transparency for funds (quarterly report data via akshare).

    ``kind``:
      - 'asset_class'  → 资产类别比例 (股票/债券/现金/...), name=类别名, ratio=%
      - 'top_holding'  →  前十大重仓, name=证券名称, ratio=%
    """
    __tablename__ = "research_asset_holdings"
    __table_args__ = (
        UniqueConstraint("asset_id", "report_date", "kind", "name", name="uq_holding_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String, ForeignKey("research_assets.id", ondelete="CASCADE"), nullable=False)
    report_date = Column(String, nullable=False)          # fund quarterly report date YYYY-MM-DD
    kind = Column(String, nullable=False)                 # asset_class | top_holding
    name = Column(String, nullable=False)
    ratio = Column(Float, nullable=True)                  # percent (e.g. 5.23 = 5.23%)
    raw = Column(Text, nullable=True)                     # original JSON payload (akshare fields)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
