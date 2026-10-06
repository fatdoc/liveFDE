from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from live_review.core.database import Base
from live_review.modules.identity.models import Admin, Workspace


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("revision > 0 AND attempt > 0"),
        CheckConstraint(
            "status IN ('queued','running','cancel_requested','succeeded','failed','canceled')"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey(Workspace.id), index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey(Admin.id))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    revision: Mapped[int] = mapped_column(default=1)
    attempt: Mapped[int] = mapped_column(default=1)
    current_stage: Mapped[str | None] = mapped_column(String(80))
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict | None] = mapped_column(JSONB)
    input_data: Mapped[dict] = mapped_column(JSONB)
    attempt_history: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")


class JobStage(Base):
    __tablename__ = "job_stages"
    __table_args__ = (
        UniqueConstraint("job_id", "name"),
        UniqueConstraint("job_id", "ordinal"),
        CheckConstraint("ordinal >= 0"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','skipped','canceled')"
        ),
        CheckConstraint("status != 'succeeded' OR artifact IS NOT NULL"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80))
    handler: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    artifact: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(String(80))
    completed_attempt: Mapped[int | None]


class Outbox(Base):
    __tablename__ = "job_outbox"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    attempt: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="pending")
    delivery_attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CallIntent(Base):
    __tablename__ = "job_call_intents"
    __table_args__ = (UniqueConstraint("job_id", "stage_id", "attempt", "call_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    stage_id: Mapped[UUID] = mapped_column(ForeignKey("job_stages.id"))
    attempt: Mapped[int]
    call_key: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default="intent")
    result: Mapped[dict | None] = mapped_column(JSONB)


class RetryKey(Base):
    __tablename__ = "job_retry_keys"
    __table_args__ = (UniqueConstraint("job_id", "actor_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey(Admin.id))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
