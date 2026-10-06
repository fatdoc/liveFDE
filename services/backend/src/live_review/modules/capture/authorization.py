"""Execution-time authorization shared by worker and explicit import retry."""

from sqlalchemy import select

from live_review.integrations.capture.contracts import CaptureError
from live_review.modules.identity.models import Admin
from live_review.modules.jobs.models import Job
from live_review.modules.sessions.models import LiveSession


def execution_actor(db, run):
    job = db.get(Job, run.job_id, populate_existing=True)
    if (
        not job
        or job.actor_id != run.actor_id
        or job.workspace_id != run.workspace_id
        or job.input_data.get("kind") != "capture_v1"
        or job.input_data.get("capture_run_id") != str(run.id)
    ):
        raise CaptureError("capture_ownership_changed")
    actor = db.scalar(
        select(Admin)
        .where(
            Admin.id == run.actor_id, Admin.active.is_(True), Admin.workspace_id == run.workspace_id
        )
        .execution_options(populate_existing=True)
    )
    session = db.scalar(
        select(LiveSession.id).where(
            LiveSession.id == run.session_id, LiveSession.workspace_id == run.workspace_id
        )
    )
    if actor is None or session is None:
        raise CaptureError("actor_not_available")
    return actor
