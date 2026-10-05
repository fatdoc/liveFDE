import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from live_review.core.database import Base


class Upload(Base):
    __tablename__ = "material_uploads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "owner_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["workspace_id", "material_id"], ["materials.workspace_id", "materials.id"]
        ),
        CheckConstraint("byte_size > 0 AND received_size >= 0 AND received_size <= byte_size"),
        CheckConstraint(
            "status IN ('pending','receiving','uploaded','finalizing',"
            "'available','failed','expired')"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admins.id"))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(30))
    declared_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    temp_key: Mapped[uuid.UUID | None]
    deduplicated: Mapped[bool] = mapped_column(Boolean, default=False)
    received_size: Mapped[int] = mapped_column(BigInteger, default=0)
    material_id: Mapped[uuid.UUID | None]
    failure_code: Mapped[str | None] = mapped_column(String(64))


class Blob(Base):
    __tablename__ = "material_blobs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "sha256"),
        CheckConstraint("size_bytes > 0"),
        UniqueConstraint("workspace_id", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[uuid.UUID] = mapped_column(unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(100))


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("purpose IN ('session_media','transcript','reference_pdf')"),
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "blob_id"], ["material_blobs.workspace_id", "material_blobs.id"]
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    blob_id: Mapped[uuid.UUID]
    filename: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionMaterial(Base):
    __tablename__ = "session_materials"
    __table_args__ = (
        CheckConstraint("role IN ('primary','reference')"),
        UniqueConstraint("workspace_id", "session_id", "material_id", "role"),
        ForeignKeyConstraint(
            ["workspace_id", "material_id"], ["materials.workspace_id", "materials.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "session_id"], ["live_sessions.workspace_id", "live_sessions.id"]
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    session_id: Mapped[uuid.UUID]
    material_id: Mapped[uuid.UUID]
    role: Mapped[str] = mapped_column(String(20))
