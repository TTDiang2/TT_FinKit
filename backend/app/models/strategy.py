from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime
from app.database import Base
import uuid, datetime

class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    description = Column(Text, default="")
    # Python source code of the Strategy subclass
    code = Column(Text, nullable=False)
    # Version number within this strategy (auto-incremented on re-import)
    version = Column(Integer, default=1)
    # JSON string of params schema: {"param_name": {"type": "int", "default": 3}}
    params_schema = Column(Text, default="{}")
    rebalance_freq = Column(String, default="monthly")  # monthly / weekly / daily
    # Is this a built-in strategy (cannot be deleted)?
    is_builtin = Column(Boolean, default=False)
    # Folder for user grouping ('' = root, '__archive__' = archive box hidden by default)
    folder = Column(String, default="")
    # JSON array of factor keys the strategy declares (parsed from docstring FACTOR_KEYS)
    factor_keys = Column(Text, nullable=True)
    # Filename the strategy was imported from (when imported via file picker / folder scan)
    source_file = Column(String, nullable=True)
    # Single-activation model: at most one strategy has this set (latest wins).
    # The signal engine runs THIS strategy when generating live signals.
    activated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
