"""Capture import calls the existing upload and association services, never writes their tables."""

import asyncio
import hashlib
import json
import shutil
from types import SimpleNamespace
from uuid import UUID

from live_review.core.errors import ApiError
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import fingerprint
from live_review.integrations.capture.recording import inspect_media
from live_review.modules.capture.files import directory, exclusive
from live_review.modules.jobs.models import Job
from live_review.modules.materials.association import associate_material
from live_review.modules.materials.schemas import LinkInput, UploadInput
from live_review.modules.materials.service import create_upload, owned_upload
from live_review.modules.materials.transfer import finalize, receive


def import_recording(db, admin, run, settings, policy, tick=lambda: None):
    job = db.get(Job, run.job_id)
    if job.input_data.get("policy_sha256") != fingerprint(policy):
        raise CaptureError("capture_config_changed")
    path = directory(policy, run.id)
    with exclusive(path / "import.lock"):
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise CaptureError("capture_not_closed")
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest.get("closed") is not True
            or manifest.get("capture_run_id") != str(run.id)
            or manifest.get("file") != "recording.mp4"
            or manifest.get("platform") != run.platform
            or manifest.get("source_ref") != run.source_ref
        ):
            raise CaptureError("invalid_manifest")
        source = path / "recording.mp4"
        if not source.is_file() or source.is_symlink():
            raise CaptureError("capture_media_missing")
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != manifest["sha256"] or source.stat().st_size != manifest["size_bytes"]:
            raise CaptureError("capture_hash_mismatch")
        inspect_media(source, policy.ffprobe)
        tick()
        if (
            not run.material_id
            and shutil.disk_usage(path).free < policy.min_free_bytes + 2 * source.stat().st_size
        ):
            raise CaptureError("disk_full")
        payload = UploadInput(
            filename=f"capture-{run.id}.mp4",
            byte_size=manifest["size_bytes"],
            sha256=digest,
            media_type="video/mp4",
            purpose="session_media",
        )
        result = create_upload(db, admin, payload, f"capture:{run.id}:0", settings)
        upload_id = UUID(result["upload_id"])
        upload = owned_upload(db, upload_id, admin)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
        if upload.status != "available":

            async def chunks():
                with source.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        tick()
                        yield chunk

            request.headers = {"content-length": str(source.stat().st_size)}
            request.stream = chunks
            asyncio.run(receive(request, db, admin, upload_id))
        tick()
        result = finalize(request, db, admin, upload_id)
        tick()
        associate_material(
            db, admin, run.session_id, LinkInput(material_id=result["material_id"], role="primary")
        )
        run.material_id = UUID(result["material_id"])
        run.manifest = manifest
        run.state, run.active, run.error_code = "imported", False, None
        db.commit()
        # Retain source even after success; retention is a separate operator decision.
        return {
            "material_id": result["material_id"],
            "capture_run_id": str(run.id),
            "transcription_status": "not_requested",
        }


def safe_import(db, admin, run, settings, policy, tick=lambda: None):
    try:
        return import_recording(db, admin, run, settings, policy, tick)
    except ApiError as exc:
        db.rollback()
        run.error_code = exc.code
        run.state = "recorded"
        db.commit()
        raise CaptureError("material_import_pending") from None
