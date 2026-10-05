"""Operator-submitted extraction and ASR stages over existing materials and LIVE-005 jobs."""

import hashlib
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.core.provider_config import (
    load_config,
    resolve_execution,
    restore_snapshot,
    snapshot,
)
from live_review.integrations.asr import (
    OfflineFixtureProvider,
    OpenAICompatibleASRProvider,
    transcribe,
)
from live_review.integrations.media import Extraction, MediaError, extract_audio
from live_review.integrations.storage.local import LocalStorage
from live_review.modules.identity.models import Admin
from live_review.modules.jobs.execution import Canceled, UnknownCall, locked
from live_review.modules.jobs.models import JobStage
from live_review.modules.jobs.service import create_job
from live_review.modules.materials.models import Blob, Material
from live_review.workers.media_artifacts import controlled, read_json, write_json
from live_review.workers.media_calls import RecordedASR


def material_source(db, workspace_id, material_id, settings):
    row = db.execute(
        select(Material, Blob)
        .join(Blob, (Material.blob_id == Blob.id) & (Material.workspace_id == Blob.workspace_id))
        .where(
            Material.id == material_id,
            Material.workspace_id == workspace_id,
            Material.purpose == "session_media",
        )
    ).first()
    if row is None:
        raise MediaError("material_not_available")
    material, blob = row
    storage = LocalStorage(settings.storage_root)
    source = storage.path("blobs", blob.storage_key)
    if source.resolve() != source or not source.is_file():
        raise MediaError("source_not_available")
    return source, blob


def submit(
    db,
    settings,
    *,
    workspace_id,
    actor_id,
    material_id,
    config_path: Path,
    allow_network=False,
    fixture_payload=None,
):
    config = load_config(config_path, environment=settings.environment)
    execution = resolve_execution(
        snapshot(config),
        "asr",
        config,
        environment=settings.environment,
        allow_network=allow_network,
    )
    actor = db.scalar(
        select(Admin).where(
            Admin.id == actor_id, Admin.workspace_id == workspace_id, Admin.active.is_(True)
        )
    )
    if actor is None:
        raise MediaError("actor_not_available")
    _, blob = material_source(db, workspace_id, material_id, settings)
    if execution.synthetic:
        OfflineFixtureProvider(fixture_payload, enabled=True, environment=settings.environment)
    elif fixture_payload is not None:
        raise MediaError("fixture_with_real_provider")
    return create_job(
        db,
        workspace_id,
        actor_id,
        [
            {"name": "extract", "handler": "media.extract"},
            {"name": "asr", "handler": "media.asr"},
        ],
        {
            "kind": "media_transcription_v1",
            "material_id": str(material_id),
            "source_sha256": blob.sha256,
            "source_size_bytes": blob.size_bytes,
            "provider_snapshot": snapshot(config).model_dump(mode="json"),
            "provider_config_path": str(config_path),
            "allow_network": allow_network is True,
            "fixture_payload": fixture_payload,
            "storage_fingerprint": hashlib.sha256(str(settings.storage_root).encode()).hexdigest(),
        },
    )


def load_context(context, settings):
    data = context.input_data()
    captured = restore_snapshot(data["provider_snapshot"])
    current = load_config(Path(data["provider_config_path"]), environment=settings.environment)
    execution = resolve_execution(
        captured,
        "asr",
        current,
        environment=settings.environment,
        allow_network=data.get("allow_network") is True,
    )
    if (
        data["storage_fingerprint"]
        != hashlib.sha256(str(settings.storage_root).encode()).hexdigest()
    ):
        raise MediaError("storage_configuration_changed")
    root = Path(settings.storage_root)
    with Session(context.engine) as db:
        job = locked(db, context.job_id, context.token)
        actor = db.get(Admin, job.actor_id)
        if not actor or not actor.active or actor.workspace_id != job.workspace_id:
            raise MediaError("actor_not_available")
        source, blob = material_source(db, job.workspace_id, UUID(data["material_id"]), settings)
        if (blob.sha256, blob.size_bytes) != (data["source_sha256"], data["source_size_bytes"]):
            raise MediaError("material_snapshot_changed")
        directory = f"jobs/{job.workspace_id}/{job.id}/{context.token}"
    controlled(root, directory)
    return data, captured, execution, root, directory, source


def cancellation(context):
    def check():
        try:
            context.heartbeat()
            return False
        except Canceled:
            return True

    return check


def extraction_handler(context, settings):
    data, captured, _, root, directory, source = load_context(context, settings)
    output_relative = directory + "/extraction"
    output = controlled(root, output_relative)
    media = captured.content.media
    extraction = extract_audio(
        source,
        input_root=root,
        output_root=output,
        segment_seconds=media.segment_seconds,
        ffmpeg_timeout_seconds=media.ffmpeg_timeout_seconds,
        ffprobe_timeout_seconds=media.ffprobe_timeout_seconds,
        max_duration_seconds=media.max_duration_seconds,
        cancel=cancellation(context),
    )
    if (extraction.source_sha256, extraction.source_size_bytes) != (
        data["source_sha256"],
        data["source_size_bytes"],
    ):
        raise MediaError("source_integrity_changed")
    reference = write_json(root, directory, extraction.model_dump(mode="json"))
    return reference | {
        "artifact_root": output_relative,
        "duration_ms": extraction.audio_duration_ms,
        "segment_count": len(extraction.segments),
        "kind": "extraction",
    }


def make_provider(execution, captured, data, settings):
    if execution.synthetic:
        return OfflineFixtureProvider(
            data["fixture_payload"], enabled=True, environment=settings.environment
        )
    route = execution.route
    return OpenAICompatibleASRProvider(
        provider=route.provider,
        model=route.model,
        base_url=route.base_url,
        api_key=execution.api_key,
        timeout_seconds=route.timeout_seconds,
        max_requests=route.max_requests,
        max_audio_duration_seconds=captured.content.media.max_duration_seconds,
        allow_network=data.get("allow_network") is True,
        environment=settings.environment,
    )


def asr_handler(context, settings):
    data, captured, execution, root, directory, _ = load_context(context, settings)
    with Session(context.engine) as db:
        prior = db.scalar(
            select(JobStage).where(
                JobStage.job_id == context.job_id,
                JobStage.name == "extract",
                JobStage.status == "succeeded",
            )
        )
        if not prior or not prior.artifact:
            raise MediaError("extraction_not_available")
        reference = prior.artifact
    extraction = Extraction.model_validate(read_json(root, reference))
    provider = RecordedASR(
        context,
        make_provider(execution, captured, data, settings),
        root,
        directory + "/calls",
        execution.route.max_requests,
        captured.content.media.max_duration_seconds,
    )
    result = transcribe(
        extraction,
        artifact_root=controlled(root, reference["artifact_root"]),
        provider=provider,
        cancel=cancellation(context),
    )
    artifact = write_json(root, directory, result.model_dump(mode="json"))
    if not result.complete:
        # Persist incomplete evidence and pointer before failing, never mark stage succeeded.
        with Session(context.engine) as db:
            locked(db, context.job_id, context.token)
            stage = db.get(JobStage, context.stage_id)
            stage.artifact = artifact | {"complete": False, "synthetic": result.synthetic}
            db.commit()
        raise MediaError("transcript_incomplete")
    return artifact | {
        "kind": "transcript",
        "complete": True,
        "synthetic": result.synthetic,
        "segment_count": len(result.segments),
        "utterance_count": len(result.utterances),
    }


def run_stage(context, settings, name):
    try:
        handler = extraction_handler if name == "media.extract" else asr_handler
        return handler(context, settings)
    except MediaError as error:
        if error.code == "canceled":
            raise Canceled from None
        if error.code == "call_result_unknown":
            raise UnknownCall from None
        raise
