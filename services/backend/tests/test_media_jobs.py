"""Real PG+FFmpeg stage integration, plus deterministic no-network intent failure cases."""

import hashlib
import json
import wave
from pathlib import Path
from uuid import uuid4

import pytest
from jobs_fixture import jobs as jobs
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.integrations.asr import ASRUnknownCall, SegmentTranscript
from live_review.integrations.media.models import Artifact, AudioSegment
from live_review.integrations.media.process import MediaError
from live_review.modules.identity.models import Admin
from live_review.modules.jobs.execution import Context, claim
from live_review.modules.jobs.models import CallIntent, Job
from live_review.modules.jobs.service import retry_job, stages_for, unknown_calls
from live_review.modules.materials.models import Blob, Material
from live_review.workers.job_runner import run_job
from live_review.workers.media_calls import RecordedASR
from live_review.workers.media_jobs import submit

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def media_job(jobs, tmp_path):
    client, headers, admin, make, engine, settings = jobs
    root = tmp_path / "storage"
    root.mkdir()
    settings = settings.model_copy(update={"storage_root": root, "job_lease_seconds": 10})
    config = tmp_path / "providers.yaml"
    config.write_text(
        (ROOT / "infra/providers.offline.example.yaml")
        .read_text()
        .replace("segment_seconds: 300", "segment_seconds: 1")
    )
    storage_key = uuid4()
    source = root / "blobs" / str(storage_key)
    source.parent.mkdir()
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 35200)
    data = source.read_bytes()
    with Session(engine, expire_on_commit=False) as db:
        blob = Blob(
            workspace_id=admin.workspace_id,
            sha256=hashlib.sha256(data).hexdigest(),
            storage_key=storage_key,
            size_bytes=len(data),
            media_type="audio/wav",
        )
        db.add(blob)
        db.flush()
        from live_review.modules.jobs.service import now

        material = Material(
            workspace_id=admin.workspace_id,
            blob_id=blob.id,
            filename="synthetic.wav",
            purpose="session_media",
            created_at=now(),
        )
        db.add(material)
        db.commit()
        mid, bid = material.id, blob.id
    fixture = {
        "segments": {
            str(index): {
                "utterances": [{"text": "synthetic", "start_ms": 0, "end_ms": 100}],
                "coverage": "full",
                "missing_words": False,
                "no_speech": False,
            }
            for index in range(3)
        }
    }

    def create(payload=None, **changes):
        args = dict(
            workspace_id=admin.workspace_id,
            actor_id=admin.id,
            material_id=mid,
            config_path=config,
            fixture_payload=fixture if payload is None else payload,
        )
        args.update(changes)
        with Session(engine) as db:
            job = submit(db, settings, **args)
            db.commit()
            return job.id

    yield create, engine, settings, root, config, fixture, admin
    with Session(engine) as db:
        db.delete(db.get(Material, mid))
        db.delete(db.get(Blob, bid))
        db.commit()


def test_real_extraction_and_asr_job_persist_artifacts(media_job):
    create, engine, settings, root, _, _, _ = media_job
    uid = create()
    run_job(engine, settings, uid, 1)
    with Session(engine) as db:
        job = db.get(Job, uid)
        assert job.status == "succeeded", job.error
        stages = stages_for(db, uid)
        assert all(stage.status == "succeeded" for stage in stages)
        assert stages[1].artifact["synthetic"] is True
        transcript = json.loads((root / stages[1].artifact["artifact_ref"]).read_text())
        assert transcript["complete"] is True
        assert [u["start_ms"] for u in transcript["utterances"]] == [0, 1000, 2000]
        calls = db.scalars(select(CallIntent).where(CallIntent.job_id == uid)).all()
        assert len(calls) == 3 and all(c.state == "known" for c in calls)
        assert all(c.result["kind"] == "response" for c in calls)
        assert "api_key" not in json.dumps(job.input_data)


def test_partial_artifact_not_success_and_retry_caches_known_calls(media_job):
    create, engine, settings, root, _, fixture, admin = media_job
    fixture["segments"]["1"] = {"fail": True}
    uid = create(fixture)
    run_job(engine, settings, uid, 1)
    with Session(engine) as db:
        job = db.get(Job, uid)
        stages = stages_for(db, uid)
        assert job.status == "failed"
        assert stages[0].status == "succeeded" and stages[1].status == "failed"
        assert stages[1].artifact["complete"] is False
        partial = json.loads((root / stages[1].artifact["artifact_ref"]).read_text())
        assert partial["status"] == "partial"
        original = stages[0].artifact
        retry_job(db, uid, admin, uuid4().hex, job.revision, "asr")
    run_job(engine, settings, uid, 2)
    with Session(engine) as db:
        stages = stages_for(db, uid)
        assert stages[0].artifact == original
        assert db.get(Job, uid).status == "failed"
        assert len(db.scalars(select(CallIntent).where(CallIntent.job_id == uid)).all()) == 3


def test_scope_disabled_actor_and_config_drift(media_job):
    create, engine, settings, _, config, _, admin = media_job
    with pytest.raises(MediaError):
        create(workspace_id=uuid4())
    with Session(engine) as db:
        db.get(Admin, admin.id).active = False
        db.commit()
    with pytest.raises(MediaError):
        create()
    with Session(engine) as db:
        db.get(Admin, admin.id).active = True
        db.commit()
    uid = create()
    config.write_text(config.read_text().replace("timeout_seconds: 60", "timeout_seconds: 61"))
    run_job(engine, settings, uid, 1)
    with Session(engine) as db:
        assert db.get(Job, uid).status == "failed"
        assert not db.scalars(select(CallIntent).where(CallIntent.job_id == uid)).all()


def test_unknown_intent_not_replayed(jobs, tmp_path):
    _, _, _, make, engine, settings = jobs
    uid = make()
    token = claim(engine, uid, 1, 30)
    with Session(engine) as db:
        sid = stages_for(db, uid)[0].id
    context = Context(engine, uid, token, sid, 30)

    class UnknownProvider:
        provider, model, synthetic = "synthetic", "unknown", True
        calls = 0

        def transcribe_segment(self, *args, **kwargs):
            self.calls += 1
            raise ASRUnknownCall

    provider = UnknownProvider()
    wrapper = RecordedASR(context, provider, tmp_path, "calls", 1, 1)
    segment = AudioSegment(
        index=0,
        start_sample=0,
        end_sample=16000,
        start_ms=0,
        end_ms=1000,
        artifact=Artifact(path="a.wav", sha256="a" * 64, size_bytes=1),
    )
    for _ in range(2):
        with pytest.raises(ASRUnknownCall):
            wrapper.transcribe_segment(segment, tmp_path / "a.wav")
    assert provider.calls == 1
    with Session(engine) as db:
        assert unknown_calls(db, uid)


def test_known_response_cache_does_not_reinvoke_provider(jobs, tmp_path):
    _, _, _, make, engine, _ = jobs
    uid = make()
    token = claim(engine, uid, 1, 30)
    with Session(engine) as db:
        sid = stages_for(db, uid)[0].id
    context = Context(engine, uid, token, sid, 30)

    class Provider:
        provider, model, synthetic = "synthetic", "known", True
        calls = 0

        def transcribe_segment(self, *args, **kwargs):
            self.calls += 1
            return SegmentTranscript(coverage="full", missing_words=False, no_speech=True)

    provider = Provider()
    wrapper = RecordedASR(context, provider, tmp_path, "calls", 1, 1)
    segment = AudioSegment(
        index=0,
        start_sample=0,
        end_sample=16000,
        start_ms=0,
        end_ms=1000,
        artifact=Artifact(path="a.wav", sha256="a" * 64, size_bytes=1),
    )
    assert wrapper.transcribe_segment(segment, tmp_path / "a.wav") == wrapper.transcribe_segment(
        segment, tmp_path / "a.wav"
    )
    assert provider.calls == 1
