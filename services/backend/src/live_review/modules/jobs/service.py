import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from live_review.core.errors import ApiError
from live_review.modules.jobs.models import CallIntent, Job, JobStage, Outbox, RetryKey

TERMINAL = {"succeeded", "failed", "canceled"}


def now():
    return datetime.now(UTC)


def stages_for(db, job_id):
    return db.scalars(
        select(JobStage).where(JobStage.job_id == job_id).order_by(JobStage.ordinal)
    ).all()


def unknown_calls(db, job_id):
    return (
        db.scalar(
            select(CallIntent.id)
            .where(CallIntent.job_id == job_id, CallIntent.state.in_(["intent", "unknown"]))
            .limit(1)
        )
        is not None
    )


def create_job(db, workspace_id, actor_id, stages: list[dict], input_data: dict):
    """Caller owns transaction. No commit: business state/job/outbox stay atomic."""
    if not stages or len(stages) > 32 or len({s["name"] for s in stages}) != len(stages):
        raise ValueError("Supply 1-32 uniquely named stages")
    if any(
        not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", s[k])
        for s in stages
        for k in ("name", "handler")
    ):
        raise ValueError("Invalid registered handler or stage name")
    from live_review.modules.identity.models import Admin

    actor = db.scalar(
        select(Admin).where(
            Admin.id == actor_id, Admin.workspace_id == workspace_id, Admin.active.is_(True)
        )
    )
    if actor is None:
        raise ValueError("Actor must belong to the workspace")
    if not isinstance(input_data, dict) or len(json.dumps(input_data, allow_nan=False)) > 262144:
        raise ValueError("Invalid job input")
    job = Job(workspace_id=workspace_id, actor_id=actor_id, input_data=input_data)
    db.add(job)
    db.flush()
    for ordinal, stage in enumerate(stages):
        db.add(
            JobStage(job_id=job.id, ordinal=ordinal, name=stage["name"], handler=stage["handler"])
        )
    db.add(Outbox(job_id=job.id, attempt=1, next_attempt_at=now()))
    db.flush()
    return job


def owned(db, job_id, admin, lock=False):
    query = select(Job).where(Job.id == job_id, Job.workspace_id == admin.workspace_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    job = db.scalar(query)
    if job is None:
        raise ApiError(404, "not_found", "任务不存在")
    return job


def view(db, job):
    stages = stages_for(db, job.id)
    return {
        "id": str(job.id),
        "revision": job.revision,
        "status": job.status,
        "current_stage": job.current_stage,
        "attempt": job.attempt,
        "attempt_history": job.attempt_history,
        "progress": None,
        "steps": [{"stage": s.name, "status": s.status, "reason": s.reason} for s in stages],
        "error": job.error,
        "can_retry": job.input_data.get("kind") != "asr_stream_v1"
        and job.status == "failed"
        and not unknown_calls(db, job.id)
        and (job.error or {}).get("code") != "execution_stop_unconfirmed",
        "cancel_requested": job.cancel_requested,
    }


def retry_job(db, job_id, admin, key, expected_revision, from_stage):
    if not key or len(key) > 128:
        raise ApiError(400, "invalid_idempotency_key", "需要有效幂等键")
    job = owned(db, job_id, admin, lock=True)
    digest = hashlib.sha256(json.dumps([expected_revision, from_stage]).encode()).hexdigest()
    saved = db.scalar(
        select(RetryKey).where(
            RetryKey.job_id == job.id, RetryKey.actor_id == admin.id, RetryKey.key == key
        )
    )
    if saved:
        if saved.request_hash != digest:
            raise ApiError(409, "idempotency_conflict", "幂等键已用于不同请求")
        return saved.response
    if job.revision != expected_revision:
        raise ApiError(409, "revision_conflict", "任务已更新", {"current_revision": job.revision})
    if (
        job.input_data.get("kind") == "asr_stream_v1"
        or job.status != "failed"
        or unknown_calls(db, job.id)
        or (job.error or {}).get("code") == "execution_stop_unconfirmed"
    ):
        raise ApiError(409, "retry_not_allowed", "任务状态或未知调用结果阻止重试")
    stages = stages_for(db, job.id)
    failed = next((stage for stage in stages if stage.status not in {"succeeded", "skipped"}), None)
    if failed is None or failed.name != from_stage:
        raise ApiError(409, "invalid_retry_stage", "必须从首个未成功阶段重试")
    job.attempt_history = [
        *job.attempt_history,
        {
            "attempt": job.attempt,
            "status": job.status,
            "error": job.error,
            "steps": [
                {
                    "stage": s.name,
                    "status": s.status,
                    "reason": s.reason,
                    "artifact": s.artifact,
                    "completed_attempt": s.completed_attempt,
                }
                for s in stages
            ],
        },
    ]
    for stage in stages[failed.ordinal :]:
        stage.status, stage.reason, stage.artifact = "pending", None, None
        stage.completed_attempt = None
    job.status, job.error, job.current_stage = "queued", None, from_stage
    job.cancel_requested = False
    job.attempt += 1
    job.revision += 1
    job.lease_token, job.lease_until = None, None
    db.add(Outbox(job_id=job.id, attempt=job.attempt, next_attempt_at=now()))
    db.flush()
    result = view(db, job)
    db.add(
        RetryKey(job_id=job.id, actor_id=admin.id, key=key, request_hash=digest, response=result)
    )
    db.commit()
    return result


def cancel_job(db, job_id, admin, expected_revision):
    job = owned(db, job_id, admin, lock=True)
    if job.status in TERMINAL:
        return view(db, job), 200
    if job.revision != expected_revision:
        raise ApiError(409, "revision_conflict", "任务已更新", {"current_revision": job.revision})
    if not job.cancel_requested:
        job.cancel_requested, job.status = True, "cancel_requested"
        job.revision += 1
    db.commit()
    return view(db, job), 202


def safe_error(code, message):
    return {"code": code, "message": message, "request_id": str(uuid4()), "details": {}}
