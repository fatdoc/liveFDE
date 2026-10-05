import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from live_review.core.errors import ApiError
from live_review.modules.materials.models import Blob, Material, Upload
from live_review.modules.materials.schemas import UploadInput


def now():
    return datetime.now(UTC)


def owned_upload(db: Session, upload_id, admin, lock=False):
    query = select(Upload).where(
        Upload.id == upload_id,
        Upload.workspace_id == admin.workspace_id,
        Upload.owner_id == admin.id,
    )
    upload = db.scalar(
        query.with_for_update().execution_options(populate_existing=True) if lock else query
    )
    if upload is None:
        raise ApiError(404, "not_found", "上传不存在")
    return upload


def create_upload(db: Session, admin, payload: UploadInput, key: str, settings):
    if not key or len(key) > 200:
        raise ApiError(400, "invalid_idempotency_key", "需要有效的Idempotency-Key")
    if payload.byte_size > settings.upload_max_bytes:
        raise ApiError(413, "upload_too_large", "文件超过后台允许的大小")
    allowed = {
        "transcript": {"text/plain"},
        "reference_pdf": {"application/pdf"},
        "session_media": {"video/mp4", "audio/wav", "audio/x-wav", "audio/mpeg"},
    }
    if payload.media_type not in allowed[payload.purpose]:
        raise ApiError(415, "unsupported_format", "材料用途与声明格式不符")
    digest = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
    query = select(Upload).where(
        Upload.workspace_id == admin.workspace_id,
        Upload.owner_id == admin.id,
        Upload.idempotency_key == key,
    )
    current = db.scalar(query)
    if current is None:
        current = Upload(
            workspace_id=admin.workspace_id,
            owner_id=admin.id,
            idempotency_key=key,
            payload_hash=digest,
            filename=payload.filename,
            byte_size=payload.byte_size,
            media_type=payload.media_type,
            purpose=payload.purpose,
            declared_sha256=payload.sha256,
            expires_at=now() + timedelta(seconds=settings.upload_ttl_seconds),
        )
        try:
            with db.begin_nested():
                db.add(current)
                db.flush()
        except IntegrityError:
            current = db.scalar(query)
    if current.payload_hash != digest:
        raise ApiError(409, "idempotency_conflict", "幂等键已用于不同上传请求")
    db.commit()
    return {
        "upload_id": str(current.id),
        "status": current.status,
        "max_bytes": settings.upload_max_bytes,
        "expires_at": current.expires_at,
    }


def claim(db: Session, upload_id, admin, mode: str, settings):
    upload = owned_upload(db, upload_id, admin, lock=True)
    if upload.status == "available":
        if mode == "finalizing":
            return upload, None
        raise ApiError(409, "upload_immutable", "已完成材料不能覆盖")
    if upload.expires_at <= now():
        upload.status = "expired"
        db.commit()
        raise ApiError(410, "upload_expired", "上传已过期，请重新初始化")
    if upload.lease_token and upload.lease_until and upload.lease_until > now():
        raise ApiError(409, "upload_busy", "该上传正在处理中")
    if mode == "finalizing" and upload.status not in {"uploaded", "failed", "finalizing"}:
        raise ApiError(409, "upload_incomplete", "请先完成上传")
    token = uuid.uuid4()
    upload.status = mode
    upload.lease_token = token
    upload.lease_until = now() + timedelta(seconds=settings.upload_lease_seconds)
    upload.failure_code = None
    if mode == "receiving":
        upload.temp_key = token
        upload.received_size = 0
    db.commit()
    return upload, token


def locked_lease(db: Session, upload_id, admin, token):
    upload = owned_upload(db, upload_id, admin, lock=True)
    if upload.lease_token != token:
        raise ApiError(409, "upload_lease_lost", "上传租约已失效，请重新查询状态")
    return upload


def record_failure(db: Session, upload_id, admin, token, code):
    db.rollback()
    upload = owned_upload(db, upload_id, admin, lock=True)
    if upload.lease_token == token:
        upload.status = "failed"
        upload.failure_code = code
        upload.lease_token = None
        upload.lease_until = None
    db.commit()


def get_material(db: Session, material_id, admin):
    material = db.scalar(
        select(Material).where(
            Material.id == material_id, Material.workspace_id == admin.workspace_id
        )
    )
    if material is None:
        raise ApiError(404, "not_found", "材料不存在")
    blob = db.scalar(
        select(Blob).where(Blob.id == material.blob_id, Blob.workspace_id == admin.workspace_id)
    )
    return material, blob


def material_json(material, blob):
    return {
        "material_id": str(material.id),
        "status": "available",
        "filename": material.filename,
        "purpose": material.purpose,
        "media_type": blob.media_type,
        "sha256": blob.sha256,
        "size_bytes": blob.size_bytes,
        "is_speech_evidence": False,
    }
