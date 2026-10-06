"""One revisioned ASR preference row per authenticated workspace."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from live_review.core.database import Base


class ASRSettings(Base):
    __tablename__ = "asr_settings"
    __table_args__ = (CheckConstraint("revision > 0"),)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    preferences: Mapped[dict] = mapped_column(JSONB)
