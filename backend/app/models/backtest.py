from sqlalchemy import Column, String, Text, Integer, Float, DateTime
from app.database import Base
import uuid, datetime

class Backtest(Base):
    """A single backtest run: strategy + params + universe snapshot + results.

    ``results`` holds the full engine output (nav_series, metrics,
    weight_history, rebalance_records, factor_view, risk_view) as JSON.
    ``data_as_of`` records the snapshot date for reproducibility.
    """
    __tablename__ = "backtests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String, nullable=False)
    strategy_version = Column(Integer, nullable=False)
    params = Column(Text, default="{}")  # JSON
    universe = Column(Text, default="[]")  # JSON: list of asset_ids
    start_date = Column(String, nullable=False)  # YYYY-MM-DD
    end_date = Column(String, nullable=False)
    rebalance_freq = Column(String, nullable=False)  # monthly / weekly
    data_as_of = Column(String, nullable=False)  # snapshot date for reproducibility
    status = Column(String, default="pending")  # pending/running/done/failed
    progress = Column(Integer, default=0)  # 0-100 回测进度
    run_pid = Column(Integer, nullable=True)  # 运行中的子进程 PID（孤儿检测用）
    error = Column(Text, nullable=True)
    results = Column(Text, nullable=True)  # JSON: full results
    # 以下三列数据库迁移早已存在，但模型曾漏声明 —— 导致
    # Backtest(group_ids=...) 直接 TypeError -> 创建回测必 500（2026-08-31）
    group_ids = Column(Text, default="[]")  # JSON: list of research group ids
    universe_count = Column(Integer, default=0)  # 展开后的标的池大小
    last_heartbeat = Column(DateTime, nullable=True)  # 运行心跳（孤儿检测）
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
