"""Workspace ASR preferences. Secrets and provider paths are never tenant settings."""

from alembic import op

revision = "0005_asr_settings"
down_revision = "0004_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE asr_settings (
 workspace_id UUID PRIMARY KEY REFERENCES workspaces(id),
 revision INTEGER NOT NULL CHECK (revision > 0),
 preferences JSONB NOT NULL
)
""")


def downgrade():
    op.drop_table("asr_settings")
