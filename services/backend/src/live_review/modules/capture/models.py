"""Business capture metadata only. Runtime media and ephemeral URLs are not DB payloads."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from live_review.core.database import Base


class CaptureRun(Base):
    __tablename__ = "capture_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key"),
        Index(
            "uq_capture_active_source",
            "workspace_id",
            "platform",
            "source_ref",
            unique=True,
            postgresql_where=text("active = true"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("admins.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("live_sessions.id"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), unique=True)
    platform: Mapped[str] = mapped_column(String(20))
    source_ref: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(40), default="queued")
    active: Mapped[bool] = mapped_column(default=True)
    stop_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    material_id: Mapped[UUID | None] = mapped_column(ForeignKey("materials.id"))
    error_code: Mapped[str | None] = mapped_column(String(80))
