"""LIVE-015 capture metadata; queue and upload tables remain the existing authorities."""

from alembic import op

revision = "0006_capture"
down_revision = "0005_asr_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE capture_runs (
        id UUID PRIMARY KEY,
        workspace_id UUID NOT NULL REFERENCES workspaces(id),
        actor_id UUID NOT NULL REFERENCES admins(id),
        session_id UUID NOT NULL REFERENCES live_sessions(id),
        job_id UUID NOT NULL UNIQUE REFERENCES jobs(id),
        platform VARCHAR(20) NOT NULL CHECK (platform IN ('douyin','wechat')),
        source_ref VARCHAR(200) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        state VARCHAR(40) NOT NULL,
        active BOOLEAN NOT NULL,
        stop_requested BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        heartbeat_at TIMESTAMPTZ,
        manifest JSONB,
        material_id UUID REFERENCES materials(id),
        error_code VARCHAR(80),
        UNIQUE (workspace_id, idempotency_key)
    );
    CREATE INDEX ix_capture_runs_workspace_id ON capture_runs(workspace_id);
    CREATE UNIQUE INDEX uq_capture_active_source
      ON capture_runs(workspace_id,platform,source_ref) WHERE active = true;
    """)


def downgrade():
    op.drop_table("capture_runs")
