import shutil
from uuid import UUID

from fastapi import APIRouter, Request

from live_review.core.auth import CurrentAdmin, Database, MutationAdmin
from live_review.core.errors import ApiError
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import load_policy, require_enabled
from live_review.integrations.capture.providers import CaptureRegistry
from live_review.modules.capture import service
from live_review.modules.capture.ingestion import safe_import
from live_review.modules.capture.schemas import ProbeInput, StartInput
from live_review.modules.identity.models import Admin

router = APIRouter(prefix="/api/v1/capture", tags=["capture"])


def policy_for(request):
    policy = load_policy(request.app.state.settings)
    require_enabled(policy)
    return policy


def translate(error):
    return ApiError(422, error.code, "采集未完成，请检查接入条件和采集状态")


@router.get("/health")
def health(request: Request, admin: CurrentAdmin):
    try:
        policy = load_policy(request.app.state.settings)
        return {
            "enabled": policy.enabled,
            "automatic_asr": False,
            "ffmpeg_ready": bool(shutil.which(policy.ffmpeg)),
            "ffprobe_ready": bool(shutil.which(policy.ffprobe)),
            "providers": {k: v.health() for k, v in CaptureRegistry(policy).providers.items()},
        }
    except CaptureError as exc:
        raise translate(exc) from None


@router.post("/probe")
def probe(data: ProbeInput, request: Request, admin: MutationAdmin):
    try:
        policy = policy_for(request)
        provider = CaptureRegistry(policy).get(data.platform)
        source = provider.probe(data.source_ref, lambda: None)
        return {
            "platform": data.platform,
            "source_ref": data.source_ref,
            "state": "waiting_for_cast"
            if data.platform == "wechat"
            else "live"
            if source.live
            else "not_live",
            "health": provider.health(),
        }
    except CaptureError as exc:
        raise translate(exc) from None


@router.post("/runs", status_code=202)
def start(data: StartInput, request: Request, admin: MutationAdmin, db: Database):
    try:
        policy = policy_for(request)
        run = service.start(db, admin, data, request.headers.get("Idempotency-Key"), policy)
        return service.view(db, run)
    except CaptureError as exc:
        raise translate(exc) from None


@router.get("/runs/{run_id}")
def status(run_id: UUID, admin: CurrentAdmin, db: Database):
    return service.view(db, service.owned(db, run_id, admin))


@router.post("/runs/{run_id}/stop", status_code=202)
def stop(run_id: UUID, admin: MutationAdmin, db: Database):
    return service.request_stop(db, service.owned(db, run_id, admin, lock=True))


@router.post("/runs/{run_id}/import")
def import_run(run_id: UUID, request: Request, admin: MutationAdmin, db: Database):
    run = service.owned(db, run_id, admin)
    job = service.reconcile(db, run)
    if job.status not in {"succeeded", "failed"}:
        raise ApiError(409, "capture_busy", "请等待采集任务停止后再重试导入")
    try:
        owner = db.get(Admin, run.actor_id)
        return safe_import(db, owner, run, request.app.state.settings, policy_for(request))
    except CaptureError as exc:
        raise translate(exc) from None
