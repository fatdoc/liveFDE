"""One recorded gateway stage over real normalized audio; legacy media stages remain intact."""

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from live_review.core.model_registry import restore_snapshot
from live_review.integrations.asr_gateway.contracts import ASRError, ASRRequest
from live_review.integrations.asr_gateway.factory import registry_for
from live_review.integrations.asr_gateway.service import ASRGateway
from live_review.integrations.media import extract_audio
from live_review.modules.asr.schemas import SettingsOutput
from live_review.modules.identity.models import Admin
from live_review.modules.jobs.execution import UnknownCall, locked
from live_review.workers.asr_recording import CloudRecorder
from live_review.workers.media_artifacts import controlled, write_json
from live_review.workers.media_jobs import cancellation, material_source


def restore_gateway(data, settings):
    registry = registry_for(settings)
    captured = restore_snapshot(data["provider_snapshot"])
    if (
        captured.config_hash != registry.snapshot().config_hash
        or data["provider_locator"] != registry.loaded.source_locator()
        or data["runtime_environment"] != settings.environment
        or data["storage_fingerprint"]
        != hashlib.sha256(str(settings.storage_root).encode()).hexdigest()
    ):
        raise ASRError("configuration_changed")
    return registry


def request_for(data, request_id, max_duration_seconds):
    prefs = SettingsOutput.model_validate(data["preferences"])
    return ASRRequest(
        request_id=str(request_id),
        speaker=prefs.speaker,
        emotion=prefs.emotion,
        punctuation=prefs.punctuation,
        privacy=prefs.privacy,
        allow_network=data["authorization"]["allow_network"],
        max_duration_seconds=max_duration_seconds,
    )


def run_stage(context, settings):
    data = context.input_data()
    registry = restore_gateway(data, settings)
    media = registry.loaded.public.media
    root = Path(settings.storage_root)
    with Session(context.engine) as db:
        job = locked(db, context.job_id, context.token)
        actor = db.get(Admin, job.actor_id)
        if not actor or not actor.active or actor.workspace_id != job.workspace_id:
            raise ASRError("actor_not_available")
        source, blob = material_source(db, job.workspace_id, UUID(data["material_id"]), settings)
        if (blob.sha256, blob.size_bytes) != (data["source_sha256"], data["source_size_bytes"]):
            raise ASRError("material_changed")
        directory = f"jobs/{job.workspace_id}/{job.id}/{context.token}"
    output = controlled(root, directory + "/extraction")
    extracted = extract_audio(
        source,
        input_root=root,
        output_root=output,
        segment_seconds=media.segment_seconds,
        max_duration_seconds=media.max_duration_seconds,
        ffmpeg_timeout_seconds=media.ffmpeg_timeout_seconds,
        ffprobe_timeout_seconds=media.ffprobe_timeout_seconds,
        cancel=cancellation(context),
    )
    if (extracted.source_sha256, extracted.source_size_bytes) != (
        data["source_sha256"],
        data["source_size_bytes"],
    ):
        raise ASRError("source_integrity_changed")
    prefs = SettingsOutput.model_validate(data["preferences"])
    gateway = ASRGateway(
        registry, prefs, data["authorization"], CloudRecorder(context, root, directory + "/calls")
    )
    request = request_for(data, context.job_id, media.max_duration_seconds)
    try:
        result = asyncio.run(gateway.transcribe_file(output / extracted.audio.path, request))
    except ASRError as error:
        if error.unknown:
            raise UnknownCall from None
        raise
    # Providers report times relative to normalized audio. Preserve source track offset.
    offset = extracted.audio_offset_ms
    if offset:
        segments = tuple(
            segment.model_copy(
                update={
                    "start_ms": segment.start_ms + offset if segment.start_ms is not None else None,
                    "end_ms": segment.end_ms + offset if segment.end_ms is not None else None,
                }
            )
            for segment in result.segments
        )
        result = result.model_copy(update={"segments": segments})
    reference = write_json(root, directory, result.model_dump(mode="json"))
    if not result.complete:
        from live_review.modules.jobs.models import JobStage

        with Session(context.engine) as db:
            locked(db, context.job_id, context.token)
            db.get(JobStage, context.stage_id).artifact = reference | {"complete": False}
            db.commit()
        raise ASRError("transcript_incomplete")
    return reference | {
        "kind": "asr_result",
        "complete": result.complete,
        "provider": result.provider,
    }
