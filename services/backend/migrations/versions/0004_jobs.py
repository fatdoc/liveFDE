"""Persistent jobs, stage artifacts, outbox and call intent safety."""

from alembic import op

revision = "0004_jobs"
down_revision = "0003_materials"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE jobs (
	id UUID NOT NULL,
	workspace_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	status VARCHAR(30) NOT NULL,
	revision INTEGER NOT NULL,
	attempt INTEGER NOT NULL,
	current_stage VARCHAR(80),
	cancel_requested BOOLEAN NOT NULL,
	lease_token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	error JSONB,
	input_data JSONB NOT NULL,
	attempt_history JSONB DEFAULT '[]' NOT NULL,
	PRIMARY KEY (id),
	CHECK (revision > 0 AND attempt > 0),
	CHECK (status IN ('queued','running','cancel_requested','succeeded','failed','canceled')),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(actor_id) REFERENCES admins (id)
)
""")
    op.execute("""
CREATE INDEX ix_jobs_workspace_id ON jobs (workspace_id)
""")
    op.execute("""
CREATE TABLE job_stages (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	ordinal INTEGER NOT NULL,
	name VARCHAR(80) NOT NULL,
	handler VARCHAR(80) NOT NULL,
	status VARCHAR(20) NOT NULL,
	artifact JSONB,
	reason VARCHAR(80),
	completed_attempt INTEGER,
	PRIMARY KEY (id),
	UNIQUE (job_id, name),
	UNIQUE (job_id, ordinal),
	CHECK (ordinal >= 0),
	CHECK (status IN ('pending','running','succeeded','failed','skipped','canceled')),
	CHECK (status != 'succeeded' OR artifact IS NOT NULL),
	FOREIGN KEY(job_id) REFERENCES jobs (id)
)
""")
    op.execute("""
CREATE INDEX ix_job_stages_job_id ON job_stages (job_id)
""")
    op.execute("""
CREATE TABLE job_outbox (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	attempt INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	delivery_attempts INTEGER NOT NULL,
	next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
	sent_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(job_id) REFERENCES jobs (id)
)
""")
    op.execute("""
CREATE INDEX ix_job_outbox_job_id ON job_outbox (job_id)
""")
    op.execute("""
CREATE TABLE job_call_intents (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	stage_id UUID NOT NULL,
	attempt INTEGER NOT NULL,
	call_key VARCHAR(128) NOT NULL,
	state VARCHAR(16) NOT NULL,
	result JSONB,
	PRIMARY KEY (id),
	UNIQUE (job_id, stage_id, attempt, call_key),
	FOREIGN KEY(job_id) REFERENCES jobs (id),
	FOREIGN KEY(stage_id) REFERENCES job_stages (id)
)
""")
    op.execute("""
CREATE TABLE job_retry_keys (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	key VARCHAR(128) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	response JSONB NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (job_id, actor_id, key),
	FOREIGN KEY(job_id) REFERENCES jobs (id),
	FOREIGN KEY(actor_id) REFERENCES admins (id)
)
""")


def downgrade():
    op.drop_table("job_retry_keys")
    op.drop_table("job_call_intents")
    op.drop_table("job_outbox")
    op.drop_table("job_stages")
    op.drop_table("jobs")
