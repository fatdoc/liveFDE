"""Authenticated settings and recorded file gateway; no raw credential/path API."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select

from live_review.core.auth import CurrentAdmin, Database, MutationAdmin
from live_review.core.errors import ApiError
from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.asr_gateway.contracts import ASRError, ASRResult
from live_review.integrations.asr_gateway.factory import create_provider, registry_for
from live_review.integrations.media import MediaError
from live_review.modules.asr.providers import provider_options
from live_review.modules.asr.schemas import SettingsInput, SettingsOutput, TranscriptionInput
from live_review.modules.asr.service import save_settings, settings_view, submit
from live_review.modules.jobs.models import Job, JobStage
from live_review.modules.jobs.service import owned, view
from live_review.workers.job_runner import run_job
from live_review.workers.media_artifacts import read_json

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])


@router.get("/providers")
def providers(request: Request, admin: CurrentAdmin):
    return provider_options(request.app.state.settings)


@router.get("/settings", response_model=SettingsOutput)
def get_settings(request: Request, admin: CurrentAdmin, db: Database):
    try:
        return settings_view(db, admin.workspace_id, request.app.state.settings)
    except ProviderConfigError as error:
        raise ApiError(503, error.code, "识别默认设置无效，请管理员检查配置") from None


@router.put("/settings", response_model=SettingsOutput)
def put_settings(data: SettingsInput, request: Request, admin: MutationAdmin, db: Database):
    return save_settings(db, admin.workspace_id, data, request.app.state.settings)


@router.get("/health")
async def health(request: Request, admin: CurrentAdmin, db: Database):
    try:
        preferences = settings_view(db, admin.workspace_id, request.app.state.settings)
        registry = registry_for(request.app.state.settings)
    except (ASRError, ProviderConfigError) as error:
        return {"config_valid": False, "health": None, "error": error.code}
    try:
        provider = create_provider(registry, preferences.provider)
        state = await provider.health()
        return {"config_valid": True, "health": state, "error": None}
    except (ASRError, ProviderConfigError) as error:
        return {"config_valid": True, "health": None, "error": error.code}
    except ImportError:
        return {"config_valid": True, "health": None, "error": "provider_dependencies_missing"}


@router.post("/transcriptions", status_code=202)
def transcribe(
    data: TranscriptionInput,
    request: Request,
    background: BackgroundTasks,
    admin: MutationAdmin,
    db: Database,
):
    settings = request.app.state.settings
    try:
        job = submit(db, admin, settings, data)
    except (ASRError, ProviderConfigError, MediaError) as error:
        raise ApiError(422, error.code, "无法创建识别任务，请检查材料与服务配置") from None
    db.commit()
    output = view(db, job)
    if settings.asr_background_runner:
        background.add_task(run_job, request.app.state.engine, settings, job.id, job.attempt)
    return output


@router.get("/transcriptions/{job_id}")
def result(job_id: UUID, request: Request, admin: CurrentAdmin, db: Database):
    job = owned(db, job_id, admin)
    if job.input_data.get("kind") not in {"asr_gateway_v1", "asr_stream_v1"}:
        raise ApiError(404, "not_found", "识别任务不存在")
    stage = db.scalar(select(JobStage).where(JobStage.job_id == job.id, JobStage.name == "asr"))
    output = None
    if stage and stage.artifact:
        output = ASRResult.model_validate(
            read_json(request.app.state.settings.storage_root, stage.artifact)
        )
    successor = db.scalar(
        select(Job.id).where(
            Job.workspace_id == admin.workspace_id,
            Job.input_data["previous_job_id"].astext == str(job.id),
        )
    )
    return {
        "job": view(db, job),
        "result": output,
        "successor_job_id": str(successor) if successor else None,
    }
