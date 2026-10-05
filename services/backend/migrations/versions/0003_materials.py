"""Independent upload leases, immutable blobs and session associations."""

import sqlalchemy as sa
from alembic import op

revision = "0003_materials"
down_revision = "0002_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "material_blobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Uuid(), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.UniqueConstraint("workspace_id", "sha256"),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("size_bytes > 0"),
    )
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("blob_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "blob_id"], ["material_blobs.workspace_id", "material_blobs.id"]
        ),
        sa.CheckConstraint("purpose IN ('session_media','transcript','reference_pdf')"),
    )
    op.create_table(
        "material_uploads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("admins.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("declared_sha256", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("temp_key", sa.Uuid()),
        sa.Column("deduplicated", sa.Boolean(), nullable=False),
        sa.Column("received_size", sa.BigInteger(), nullable=False),
        sa.Column("material_id", sa.Uuid()),
        sa.Column("failure_code", sa.String(64)),
        sa.UniqueConstraint("workspace_id", "owner_id", "idempotency_key"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "material_id"], ["materials.workspace_id", "materials.id"]
        ),
        sa.CheckConstraint("byte_size > 0 AND received_size >= 0 AND received_size <= byte_size"),
        sa.CheckConstraint(
            "status IN ('pending','receiving','uploaded','finalizing',"
            "'available','failed','expired')"
        ),
    )
    op.create_table(
        "session_materials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.UniqueConstraint("workspace_id", "session_id", "material_id", "role"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "material_id"], ["materials.workspace_id", "materials.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"], ["live_sessions.workspace_id", "live_sessions.id"]
        ),
        sa.CheckConstraint("role IN ('primary','reference')"),
    )


def downgrade():
    op.drop_table("session_materials")
    op.drop_table("material_uploads")
    op.drop_table("materials")
    op.drop_table("material_blobs")
