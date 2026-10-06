from uuid import UUID

from capture_fixture import av_file as av_file
from capture_fixture import capture_env as capture_env
from capture_fixture import closed_fixture, start_run
from capture_fixture import materials as materials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from live_review.main import app
from live_review.modules.jobs.models import Job
from live_review.modules.materials.models import Material, SessionMaterial
from live_review.workers.job_runner import run_job


def test_closed_recovery_import_dedup_session_asr(capture_env, av_file):
    fixture, settings, root = capture_env
    client, headers, admin, _, _ = fixture
    run, _ = start_run(fixture)
    closed_fixture(root, run, av_file)
    run_job(app.state.engine, settings, run["job_id"], 1)
    path = f"/api/v1/capture/runs/{run['capture_run_id']}"
    first = client.get(path).json()
    assert first["state"] == "imported", first
    assert first["transcription_status"] == "not_requested"
    for _ in range(2):
        again = client.post(path + "/import", headers=headers)
        assert again.status_code == 200, again.text
        assert again.json()["material_id"] == first["material_id"]
    assert (root / run["capture_run_id"] / "recording.mp4").exists()
    with Session(app.state.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Material)
                .where(Material.workspace_id == admin.workspace_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SessionMaterial)
                .where(SessionMaterial.workspace_id == admin.workspace_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Job).where(Job.workspace_id == admin.workspace_id)
            )
            == 1
        )
    content = client.get(f"/api/v1/materials/{first['material_id']}/content")
    assert content.status_code == 200
    # Existing ASR route sees the material but requires saved settings, not a capture failure.
    response = client.post(
        "/api/v1/asr/transcriptions",
        headers=headers,
        json={"material_id": first["material_id"], "expected_revision": 0},
    )
    assert response.status_code == 409
    assert client.get(path).json()["state"] == "imported"
    # Explicit manual submission reaches the unchanged ASR queue; no model executes.
    from pathlib import Path

    config = Path(__file__).resolve().parents[3] / "config/asr.example.yaml"
    (settings.model_config_dir / "models.yaml").write_text(
        config.read_text().replace("enabled: false", "enabled: true")
    )
    assert (
        client.put(
            "/api/v1/asr/settings", headers=headers, json={"expected_revision": 0}
        ).status_code
        == 200
    )
    submitted = client.post(
        "/api/v1/asr/transcriptions",
        headers=headers,
        json={"material_id": first["material_id"], "expected_revision": 1},
    )
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["status"] == "queued"
    assert client.get(path).json()["state"] == "imported"


def test_unclosed_and_tampered_never_import(capture_env, av_file):
    fixture, _, root = capture_env
    client, headers, _, _, _ = fixture
    run, _ = start_run(fixture)
    with Session(app.state.engine) as db:
        db.get(Job, UUID(run["job_id"])).status = "failed"
        db.commit()
    endpoint = f"/api/v1/capture/runs/{run['capture_run_id']}/import"
    assert client.post(endpoint, headers=headers).json()["code"] == "capture_not_closed"
    closed_fixture(root, run, av_file)
    with (root / run["capture_run_id"] / "recording.mp4").open("ab") as stream:
        stream.write(b"tamper")
    assert client.post(endpoint, headers=headers).json()["code"] == "capture_hash_mismatch"


def test_finalize_commit_before_association_crash_recovers(capture_env, av_file, monkeypatch):
    import pytest

    from live_review.integrations.capture.policy import load_policy
    from live_review.modules.capture import ingestion
    from live_review.modules.capture.models import CaptureRun

    fixture, settings, root = capture_env
    _, _, admin, _, _ = fixture
    run, _ = start_run(fixture)
    closed_fixture(root, run, av_file)
    original = ingestion.associate_material

    def lost_after_finalize(*args, **kwargs):
        raise RuntimeError("synthetic_crash_after_finalize_commit")

    monkeypatch.setattr(ingestion, "associate_material", lost_after_finalize)
    with Session(app.state.engine) as db:
        row = db.get(CaptureRun, UUID(run["capture_run_id"]))
        with pytest.raises(RuntimeError):
            ingestion.import_recording(db, admin, row, settings, load_policy(settings))
    monkeypatch.setattr(ingestion, "associate_material", original)
    with Session(app.state.engine) as db:
        row = db.get(CaptureRun, UUID(run["capture_run_id"]))
        result = ingestion.import_recording(db, admin, row, settings, load_policy(settings))
        assert result["material_id"]
        assert (
            db.scalar(
                select(func.count())
                .select_from(Material)
                .where(Material.workspace_id == admin.workspace_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SessionMaterial)
                .where(SessionMaterial.workspace_id == admin.workspace_id)
            )
            == 1
        )
