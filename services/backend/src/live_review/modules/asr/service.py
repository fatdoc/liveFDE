"""Revisioned preferences, explicit cloud grants, and immutable gateway job submission."""

import hashlib

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from live_review.core.errors import ApiError
from live_review.integrations.asr_gateway.factory import MODEL_IDS, registry_for
from live_review.modules.asr.models import ASRSettings
from live_review.modules.asr.schemas import Preferences, SettingsOutput
from live_review.modules.jobs.service import create_job
from live_review.workers.media_jobs import material_source


def settings_view(db, workspace_id):
    row = db.get(ASRSettings, workspace_id)
    return SettingsOutput(
        **(row.preferences if row else Preferences().model_dump()),
        revision=row.revision if row else 0,
    )


def save_settings(db, workspace_id, data):
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
    return settings_view(db, workspace_id)


def authorization(preferences, data):
    if data.expected_revision != preferences.revision:
        raise ApiError(409, "revision_conflict", "ASR设置已更改，请确认最新设置")
    needs_cloud = preferences.provider == "tencent" or preferences.allow_cloud_fallback
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
    preferences = settings_view(db, admin.workspace_id)
    grant = authorization(preferences, data)
    registry = registry_for(settings)
    descriptor = registry.get(MODEL_IDS[preferences.provider])
    if not descriptor.route.enabled:
        raise ApiError(422, "asr_provider_disabled", "识别服务尚未启用")
    if preferences.allow_cloud_fallback:
        fallback = registry.get(MODEL_IDS["tencent"])
        if not fallback.route.enabled:
            raise ApiError(422, "fallback_provider_disabled", "云回退尚未启用")
    return registry, {
        "kind": "asr_gateway_v1",
        "preferences": preferences.model_dump(),
        "authorization": grant,
        "provider_snapshot": registry.snapshot().model_dump(mode="json"),
        "provider_locator": registry.loaded.source_locator(),
        "runtime_environment": settings.environment,
        "storage_fingerprint": hashlib.sha256(str(settings.storage_root).encode()).hexdigest(),
    }


def submit(db, admin, settings, data):
    _, payload = prepare(db, admin, settings, data)
    _, blob = material_source(db, admin.workspace_id, data.material_id, settings)
    payload.update(
        material_id=str(data.material_id),
        source_sha256=blob.sha256,
        source_size_bytes=blob.size_bytes,
    )
    return create_job(
        db, admin.workspace_id, admin.id, [{"name": "asr", "handler": "asr.gateway"}], payload
    )
