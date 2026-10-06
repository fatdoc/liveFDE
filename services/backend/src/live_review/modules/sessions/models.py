from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from live_review.core.database import Base


class LiveSession(Base):
    __tablename__ = "live_sessions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_session_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "streamer_id"], ["streamers.workspace_id", "streamers.id"]
        ),
        CheckConstraint("revision >= 1", name="ck_session_revision"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_session_duration"),
        CheckConstraint("timezone = 'Asia/Shanghai'", name="ck_session_timezone"),
        CheckConstraint(
            "time_source IN ('user_entered', 'media_metadata')", name="ck_session_time_source"
        ),
        CheckConstraint(
            "(time_precision = 'date' AND started_at IS NULL) OR "
            "(time_precision IN ('minute', 'second') AND started_at IS NOT NULL)",
            name="ck_session_time_precision",
        ),
        CheckConstraint(
            "started_at IS NULL OR "
            "(started_at AT TIME ZONE 'Asia/Shanghai')::date = session_local_date",
            name="ck_session_local_date",
        ),
        Index("ix_session_workspace_date", "workspace_id", "session_local_date"),
        Index(
            "ix_session_workspace_streamer_date",
            "workspace_id",
            "streamer_id",
            "session_local_date",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID]
    streamer_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(30))
    session_local_date: Mapped[date]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_precision: Mapped[str] = mapped_column(String(10), default="date")
    time_source: Mapped[str] = mapped_column(String(30), default="user_entered")
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Shanghai")
    duration_ms: Mapped[int | None]
    processing_status: Mapped[str] = mapped_column(String(30), default="pending")
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
