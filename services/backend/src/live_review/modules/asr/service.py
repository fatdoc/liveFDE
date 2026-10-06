"""Revisioned preferences, explicit cloud grants, and immutable gateway job submission."""

import hashlib

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from live_review.core.errors import ApiError
from live_review.integrations.asr_gateway.factory import MODEL_IDS, registry_for
from live_review.modules.asr.models import ASRSettings
from live_review.modules.asr.policy import load_policy, policy_snapshot
from live_review.modules.asr.schemas import SettingsOutput
from live_review.modules.jobs.models import Job
from live_review.modules.jobs.service import create_job, owned, unknown_calls, view
from live_review.modules.materials.models import Material
from live_review.workers.media_jobs import material_source


def settings_view(db, workspace_id, settings=None):
    row = db.get(ASRSettings, workspace_id)
    return SettingsOutput(
        **(row.preferences if row else load_policy(settings).defaults.model_dump()),
        revision=row.revision if row else 0,
    )


def save_settings(db, workspace_id, data, settings=None):
    fields = data.model_dump(exclude={"expected_revision"})
    if data.expected_revision == 0:
        db.add(ASRSettings(workspace_id=workspace_id, revision=1, preferences=fields))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ApiError(409, "revision_conflict", "设置已被修改，请刷新后重试") from None
    else:
        changed = db.execute(
            update(ASRSettings)
            .where(
                ASRSettings.workspace_id == workspace_id,
                ASRSettings.revision == data.expected_revision,
            )
            .values(preferences=fields, revision=data.expected_revision + 1)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise ApiError(409, "revision_conflict", "设置已被修改，请刷新后重试")
        db.commit()
    db.expire_all()
    return settings_view(db, workspace_id, settings)


def authorization(preferences, data):
    if data.expected_revision != preferences.revision:
        raise ApiError(409, "revision_conflict", "ASR设置已更改，请确认最新设置")
    needs_cloud = preferences.provider == "tencent" or (
        preferences.allow_cloud_fallback and data.allow_network
    )
    if needs_cloud and (
        preferences.privacy != "cloud_allowed"
        or not data.allow_network
        or data.max_requests is None
        or data.max_cost_usd is None
    ):
        raise ApiError(422, "cloud_authorization_required", "云识别需要本次授权及请求、金额预算")
    # A local-only task cannot smuggle a cloud grant through otherwise ignored fields.
    if preferences.privacy == "local_only" and data.allow_network:
        raise ApiError(422, "local_only_forbids_cloud", "仅本地模式禁止云调用授权")
    return {
        "allow_network": needs_cloud and data.allow_network,
        "max_requests": data.max_requests if needs_cloud else 0,
        "max_cost_usd": data.max_cost_usd if needs_cloud else None,
    }


def prepare(db, admin, settings, data):
    preferences = settings_view(db, admin.workspace_id, settings)
    grant = authorization(preferences, data)
    if preferences.revision == 0:
        raise ApiError(409, "settings_save_required", "请先保存识别设置，再开始试用")
    registry = registry_for(settings)
    descriptor = registry.get(MODEL_IDS[preferences.provider])
    if not descriptor.route.enabled:
        raise ApiError(422, "asr_provider_disabled", "识别服务尚未启用")
    if preferences.allow_cloud_fallback and grant["allow_network"]:
        fallback = registry.get(MODEL_IDS["tencent"])
        if not fallback.route.enabled:
            raise ApiError(422, "fallback_provider_disabled", "云回退尚未启用")
    return registry, {
        "kind": "asr_gateway_v1",
        "gateway_policy_snapshot": policy_snapshot(settings),
        "preferences": preferences.model_dump(),
        "authorization": grant,
        "provider_snapshot": registry.snapshot().model_dump(mode="json"),
        "provider_locator": registry.loaded.source_locator(),
        "runtime_environment": settings.environment,
        "storage_fingerprint": hashlib.sha256(str(settings.storage_root).encode()).hexdigest(),
    }


def submit(db, admin, settings, data):
    # Serialize submissions for this material, including first submissions from another tab.
    material = db.scalar(
        select(Material)
        .where(Material.id == data.material_id, Material.workspace_id == admin.workspace_id)
        .with_for_update()
    )
    if material is None:
        raise ApiError(422, "material_not_available", "材料不存在")
    if data.previous_job_id is not None:
        previous = owned(db, data.previous_job_id, admin, lock=True)
        if previous.input_data.get("kind") != "asr_gateway_v1" or previous.input_data.get(
            "material_id"
        ) != str(data.material_id):
            raise ApiError(409, "asr_previous_material_mismatch", "原任务不属于当前材料")
        if previous.revision != data.expected_previous_revision:
            raise ApiError(409, "revision_conflict", "原任务状态已改变，请刷新")
        successor = db.scalar(
            select(Job.id).where(
                Job.workspace_id == admin.workspace_id,
                Job.input_data["previous_job_id"].astext == str(previous.id),
            )
        )
        if successor:
            raise ApiError(
                409,
                "asr_successor_exists",
                "该失败任务已有后续转写，请查询新任务",
                {"job_id": str(successor)},
            )
        if not view(db, previous)["can_retry"]:
            raise ApiError(409, "retry_not_allowed", "原任务未确认失败或结果未知，不能重新转写")
    related = db.scalars(
        select(Job).where(
            Job.workspace_id == admin.workspace_id,
            Job.input_data["material_id"].astext == str(data.material_id),
            Job.input_data["kind"].astext == "asr_gateway_v1",
        )
    ).all()
    for old in related:
        if (
            old.status in {"queued", "running", "cancel_requested"}
            or unknown_calls(db, old.id)
            or (old.error or {}).get("code") == "execution_stop_unconfirmed"
        ):
            raise ApiError(
                409,
                "asr_material_task_unresolved",
                "当前材料有进行中或结果未确认的转写，请先查询原任务",
                {"job_id": str(old.id)},
            )
    _, payload = prepare(db, admin, settings, data)
    _, blob = material_source(db, admin.workspace_id, data.material_id, settings)
    payload.update(
        material_id=str(data.material_id),
        source_sha256=blob.sha256,
        source_size_bytes=blob.size_bytes,
    )
    if data.previous_job_id is not None:
        payload["previous_job_id"] = str(data.previous_job_id)
    return create_job(
        db, admin.workspace_id, admin.id, [{"name": "asr", "handler": "asr.gateway"}], payload
    )
