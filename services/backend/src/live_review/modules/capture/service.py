import base64
import binascii
import hashlib
import json
import shutil
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError

from live_review.core.errors import ApiError
from live_review.integrations.capture.policy import fingerprint
from live_review.modules.capture.credentials import CredentialStore
from live_review.modules.capture.executor_health import execution_health
from live_review.modules.capture.models import CaptureRun
from live_review.modules.capture.readiness import platform_conditions
from live_review.modules.jobs.models import Job
from live_review.modules.jobs.service import TERMINAL, create_job, now
from live_review.modules.sessions.service import get_session


def owned(db, run_id, admin, lock=False):
    query = select(CaptureRun).where(
        CaptureRun.id == run_id, CaptureRun.workspace_id == admin.workspace_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    run = db.scalar(query)
    if run is None:
        raise ApiError(404, "not_found", "采集不存在")
    return run


def reconcile(db, run):
    job = db.get(Job, run.job_id)
    if job.status in TERMINAL and run.active:
        run.active = False
        if job.status in {"failed", "canceled"} and not run.manifest:
            run.state = "canceled" if job.status == "canceled" else "failed"
            run.error_code = run.error_code or (
                "canceled" if job.status == "canceled" else "worker_interrupted"
            )
        db.commit()
    return job


def view(db, run):
    job = reconcile(db, run)
    return {
        "capture_run_id": str(run.id),
        "job_id": str(run.job_id),
        "created_at": run.created_at,
        "session_id": str(run.session_id),
        "platform": run.platform,
        "source_ref": run.source_ref,
        "state": run.state,
        "job_status": job.status,
        "stop_requested": run.stop_requested,
        "heartbeat_at": run.heartbeat_at,
        "manifest": run.manifest,
        "error_code": run.error_code,
        "material_id": str(run.material_id) if run.material_id else None,
        "recording_status": ("recorded" if run.manifest else run.state),
        "import_status": "imported" if run.material_id else "pending",
        "transcription_status": "not_requested",
        "automatic_asr": False,
    }


def start(db, admin, data, key, policy, *, settings=None):
    if not key or len(key) > 128:
        raise ApiError(400, "invalid_idempotency_key", "需要有效幂等键")
    get_session(db, admin.workspace_id, data.session_id)
    digest = hashlib.sha256(
        json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    query = select(CaptureRun).where(
        CaptureRun.workspace_id == admin.workspace_id, CaptureRun.idempotency_key == key
    )
    existing = db.scalar(query)
    if existing:
        if existing.request_hash != digest:
            raise ApiError(409, "idempotency_conflict", "幂等键已用于不同采集")
        return existing
    if data.platform not in policy.allowed_platforms:
        raise ApiError(503, "capture_platform_disabled", "当前配置未开放该平台采集")
    if policy.execution_mode == "native" and (
        settings is None or not execution_health(settings, policy)["ready"]
    ):
        raise ApiError(503, "capture_executor_unavailable", "采集执行器未就绪，请稍后重试")
    if policy.execution_mode == "native":
        blockers = platform_conditions(
            policy,
            data.platform,
            execution_health(settings, policy),
            bool(shutil.which(policy.ffmpeg)),
            bool(shutil.which(policy.ffprobe)),
            douyin_cookie=(
                CredentialStore(settings, admin.workspace_id).read().cookie
                if data.platform == "douyin"
                else ""
            ),
        )["blockers"]
        if blockers:
            raise ApiError(503, blockers[0]["code"], blockers[0]["message"])
    # Clean terminal activity claims, without using file-size heuristics.
    active = db.scalars(
        select(CaptureRun).where(
            CaptureRun.workspace_id == admin.workspace_id, CaptureRun.active.is_(True)
        )
    ).all()
    for run in active:
        reconcile(db, run)
    run_id = uuid4()
    try:
        with db.begin_nested():
            job = create_job(
                db,
                admin.workspace_id,
                admin.id,
                [
                    {"name": "record", "handler": "capture.record"},
                    {"name": "import", "handler": "capture.import"},
                ],
                {
                    "kind": "capture_v1",
                    "capture_run_id": str(run_id),
                    "policy_sha256": fingerprint(policy),
                },
            )
            run = CaptureRun(
                id=run_id,
                workspace_id=admin.workspace_id,
                actor_id=admin.id,
                session_id=data.session_id,
                job_id=job.id,
                platform=data.platform,
                source_ref=data.source_ref,
                idempotency_key=key,
                request_hash=digest,
                created_at=now(),
            )
            db.add(run)
            db.flush()
    except IntegrityError:
        existing = db.scalar(query)
        if existing and existing.request_hash == digest:
            return existing
        raise ApiError(409, "capture_already_active", "相同来源已在采集，或幂等键冲突") from None
    db.commit()
    return run


def request_stop(db, run):
    reconcile(db, run)
    if run.active:
        run.stop_requested = True
        db.commit()
    return view(db, run)


def list_runs(db, admin, session_id, limit=20, cursor=None):
    get_session(db, admin.workspace_id, session_id)
    query = select(CaptureRun).where(
        CaptureRun.workspace_id == admin.workspace_id, CaptureRun.session_id == session_id
    )
    if cursor:
        try:
            payload = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if not isinstance(payload, dict) or any(
                not isinstance(payload.get(key), str) for key in ("session_id", "created_at", "id")
            ):
                raise ValueError
            if payload["session_id"] != str(session_id):
                raise ValueError
            boundary_time = datetime.fromisoformat(payload["created_at"])
            boundary_id = UUID(payload["id"])
            if boundary_time.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError, KeyError, binascii.Error):
            raise ApiError(422, "invalid_cursor", "采集列表分页标记无效") from None
        query = query.where(
            tuple_(CaptureRun.created_at, CaptureRun.id) < tuple_(boundary_time, boundary_id)
        )
    rows = db.scalars(
        query.order_by(CaptureRun.created_at.desc(), CaptureRun.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        payload = {
            "session_id": str(session_id),
            "created_at": last.created_at.isoformat(),
            "id": str(last.id),
        }
        next_cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return {"items": [view(db, run) for run in page], "next_cursor": next_cursor}
