"""Workspace-scoped streamers and dated live sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_sessions"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "streamers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("platform_ref", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_streamer_workspace_id"),
    )
    op.create_index("ix_streamers_workspace_id", "streamers", ["workspace_id"])
    op.create_table(
        "live_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("streamer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("session_local_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_precision", sa.String(10), nullable=False),
        sa.Column("time_source", sa.String(30), nullable=False),
        sa.Column("timezone", sa.String(40), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("processing_status", sa.String(30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_session_workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "streamer_id"], ["streamers.workspace_id", "streamers.id"]
        ),
        sa.CheckConstraint("revision >= 1", name="ck_session_revision"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_session_duration"),
        sa.CheckConstraint("timezone = 'Asia/Shanghai'", name="ck_session_timezone"),
        sa.CheckConstraint(
            "time_source IN ('user_entered', 'media_metadata')", name="ck_session_time_source"
        ),
        sa.CheckConstraint(
            "(time_precision = 'date' AND started_at IS NULL) OR "
            "(time_precision IN ('minute', 'second') AND started_at IS NOT NULL)",
            name="ck_session_time_precision",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR "
            "(started_at AT TIME ZONE 'Asia/Shanghai')::date = session_local_date",
            name="ck_session_local_date",
        ),
    )
    op.create_index(
        "ix_session_workspace_date", "live_sessions", ["workspace_id", "session_local_date"]
    )
    op.create_index(
        "ix_session_workspace_streamer_date",
        "live_sessions",
        ["workspace_id", "streamer_id", "session_local_date"],
    )


def downgrade():
    op.drop_table("live_sessions")
    op.drop_table("streamers")
