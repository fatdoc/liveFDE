import os
import time
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from live_review.core.errors import ApiError
from live_review.integrations.storage.local import LocalStorage
from live_review.modules.materials.models import Blob, Material
from live_review.modules.materials.service import (
    claim,
    get_material,
    locked_lease,
    now,
    owned_upload,
    record_failure,
)
from live_review.modules.materials.validation import validate_file


def transfer_pulse(db, admin, upload_id, token, settings, tick):
    last = 0.0

    def pulse():
        nonlocal last
        if tick is None:
            return
        tick()
        current_time = time.monotonic()
        if current_time - last >= min(1.0, settings.upload_lease_seconds / 3):
            current = locked_lease(db, upload_id, admin, token)
            current.lease_until = now() + timedelta(seconds=settings.upload_lease_seconds)
            db.commit()
            last = current_time

    return pulse


async def receive(request: Request, db, admin, upload_id, *, tick=None):
    settings = request.app.state.settings
    storage = LocalStorage(settings.storage_root)
    upload = owned_upload(db, upload_id, admin)
    length = request.headers.get("content-length")
    if (
        not length
        or len(length) > 20
        or not length.isascii()
        or not length.isdigit()
        or int(length) != upload.byte_size
    ):
        raise ApiError(422, "content_length_mismatch", "Content-Length须与声明大小一致")
    upload, token = claim(db, upload_id, admin, "receiving", settings)
    partial = storage.prepare("uploads", token, ".part")
    complete = storage.path("uploads", token)
    count = 0
    pulse = transfer_pulse(db, admin, upload_id, token, settings, tick)
    try:
        with partial.open("xb") as output:
            async for chunk in request.stream():
                pulse()
                count += len(chunk)
                if count > upload.byte_size or count > settings.upload_max_bytes:
                    raise ApiError(413, "upload_too_large", "接收数据超出声明大小")
                await run_in_threadpool(output.write, chunk)
            output.flush()
            os.fsync(output.fileno())
        if count != upload.byte_size:
            raise ApiError(422, "file_size_mismatch", "上传中断或大小不符")
        os.replace(partial, complete)
        current = locked_lease(db, upload_id, admin, token)
        current.status = "uploaded"
        current.received_size = count
        current.lease_token = None
        current.lease_until = None
        db.commit()
    except Exception as exc:
        partial.unlink(missing_ok=True)
        # Complete bytes remain recoverable if the final DB write failed.
        try:
            record_failure(db, upload_id, admin, token, getattr(exc, "code", "upload_failed"))
        except Exception:
            db.rollback()
        raise
    return {"upload_id": str(upload_id), "status": "uploaded", "received_size": count}


def finalize(request: Request, db, admin, upload_id, *, tick=None, publish_tick=None):
    settings = request.app.state.settings
    storage = LocalStorage(settings.storage_root)
    upload, token = claim(db, upload_id, admin, "finalizing", settings)
    if token is None:
        _, blob = get_material(db, upload.material_id, admin)
        return finalized_json(upload, blob)
    candidate = None
    pulse = transfer_pulse(db, admin, upload_id, token, settings, tick)
    try:
        source = storage.path("uploads", upload.temp_key) if upload.temp_key else None
        if source is None or not source.is_file():
            raise ApiError(409, "upload_incomplete", "完整上传文件不存在，请重新PUT")
        digest = validate_file(
            source,
            upload.byte_size,
            upload.declared_sha256,
            upload.media_type,
            upload.purpose,
            settings.ffprobe_path,
            **({"tick": pulse} if tick is not None else {}),
        )
        # Each lease writes a unique immutable candidate. A stale finalizer cannot
        # overwrite a later successful attempt, even after a lease takeover.
        candidate = storage.promote_copy(
            source, token, **({"tick": pulse} if tick is not None else {})
        )
        # Do not use the throttled lease pulse at publication boundaries.
        checkpoint = publish_tick if publish_tick is not None else tick
        if checkpoint is not None:
            checkpoint()
        current = locked_lease(db, upload_id, admin, token)
        query = select(Blob).where(Blob.workspace_id == admin.workspace_id, Blob.sha256 == digest)
        blob = db.scalar(query)
        deduplicated = blob is not None
        if blob is None:
            blob = Blob(
                workspace_id=admin.workspace_id,
                sha256=digest,
                storage_key=token,
                size_bytes=current.byte_size,
                media_type=current.media_type,
            )
            try:
                with db.begin_nested():
                    db.add(blob)
                    db.flush()
            except IntegrityError:
                blob = db.scalar(query)
                deduplicated = True
        if blob is None or not storage.path("blobs", blob.storage_key).is_file():
            raise ApiError(503, "blob_unavailable", "已有文件暂不可读取")
        material = Material(
            workspace_id=admin.workspace_id,
            blob_id=blob.id,
            filename=current.filename,
            purpose=current.purpose,
            created_at=now(),
        )
        db.add(material)
        db.flush()
        current.material_id = material.id
        current.status = "available"
        current.deduplicated = deduplicated
        current.lease_token = None
        current.lease_until = None
        if checkpoint is not None:
            checkpoint()
        db.commit()
        # No deletion before commit: rollback/restart may need the uploaded bytes.
        # Cleanup failure cannot turn a successful finalization into failed state.
        try:
            source.unlink(missing_ok=True)
            if deduplicated:
                candidate.unlink(missing_ok=True)
        except OSError:
            pass
        return finalized_json(current, blob)
    except Exception as exc:
        try:
            record_failure(db, upload_id, admin, token, getattr(exc, "code", "finalize_failed"))
        except Exception:
            db.rollback()
        # Keep source and candidate for a recoverable retry; retention GC is separate.
        raise


def finalized_json(upload, blob):
    return {
        "material_id": str(upload.material_id),
        "status": "available",
        "sha256": blob.sha256,
        "size_bytes": blob.size_bytes,
        "deduplicated": upload.deduplicated,
    }
