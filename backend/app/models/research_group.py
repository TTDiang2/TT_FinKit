"""User-defined research asset groups (标的组合).

A named subset of the user's pooled/watchlist assets, e.g. 全宽基指数 /
全地域市场 / 大类资产池. Strategies can later scope their universe to one
group instead of the whole pool.
"""
import uuid
import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class ResearchGroup(Base):
    __tablename__ = "research_groups"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_group_user_name"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    note = Column(String, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    members = relationship("ResearchGroupMember", cascade="all, delete-orphan",
                           backref="group", lazy="selectin")


class ResearchGroupMember(Base):
    __tablename__ = "research_group_members"

    group_id = Column(String, ForeignKey("research_groups.id", ondelete="CASCADE"),
                      primary_key=True)
    asset_id = Column(String, ForeignKey("research_assets.id", ondelete="CASCADE"),
                      primary_key=True)
