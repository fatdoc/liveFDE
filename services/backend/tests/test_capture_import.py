from uuid import UUID

import pytest
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


@pytest.mark.parametrize(
    "change,expected",
    [
        ("disabled", "actor_not_available"),
        ("workspace", "actor_not_available"),
        ("job_actor", "capture_ownership_changed"),
    ],
)
def test_execution_and_manual_import_revalidate_actor(capture_env, av_file, change, expected):
    from uuid import uuid4

    from materials_fixture import ORIGIN, PASSWORD

    from live_review.modules.capture.models import CaptureRun
    from live_review.modules.identity.models import Admin
    from live_review.modules.identity.security import hasher

    fixture, settings, root = capture_env
    client, _, admin, _, stranger = fixture
    run, _ = start_run(fixture)
    manifest = closed_fixture(root, run, av_file)
    with Session(app.state.engine) as db:
        alternate = Admin(
            workspace_id=admin.workspace_id,
            username=uuid4().hex,
            display_name="Authorized retry operator",
            password_hash=hasher.hash(PASSWORD),
        )
        username = alternate.username
        db.add(alternate)
        if change == "disabled":
            db.get(Admin, admin.id).active = False
        elif change == "workspace":
            db.get(Admin, admin.id).workspace_id = stranger.workspace_id
        else:
            db.get(Job, UUID(run["job_id"])).actor_id = stranger.id
        row = db.get(CaptureRun, UUID(run["capture_run_id"]))
        row.manifest, row.state = manifest, "recorded"
        db.commit()
    run_job(app.state.engine, settings, run["job_id"], 1)
    login = client.post(
        "/api/v1/auth/login", headers=ORIGIN, json={"username": username, "password": PASSWORD}
    )
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    endpoint = f"/api/v1/capture/runs/{run['capture_run_id']}"
    response = client.post(endpoint + "/import", headers=headers)
    assert response.status_code == 422 and response.json()["code"] == expected
    status = client.get(endpoint).json()
    assert status["error_code"] == expected and status["state"] == "recorded"
    assert status["material_id"] is None and status["manifest"] == manifest
    with Session(app.state.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Material)
                .where(Material.workspace_id == admin.workspace_id)
            )
            == 0
        )


def test_import_capture_error_persisted_without_losing_recording(capture_env, av_file):
    from live_review.modules.capture.models import CaptureRun

    fixture, _, root = capture_env
    client, headers, _, _, _ = fixture
    run, _ = start_run(fixture)
    manifest = closed_fixture(root, run, av_file)
    with Session(app.state.engine) as db:
        db.get(Job, UUID(run["job_id"])).status = "failed"
        row = db.get(CaptureRun, UUID(run["capture_run_id"]))
        row.manifest, row.state = manifest, "recorded"
        db.commit()
    with (root / run["capture_run_id"] / "recording.mp4").open("ab") as stream:
        stream.write(b"synthetic-corruption")
    endpoint = f"/api/v1/capture/runs/{run['capture_run_id']}"
    assert client.post(endpoint + "/import", headers=headers).status_code == 422
    status = client.get(endpoint).json()
    assert status["error_code"] == "capture_hash_mismatch"
    assert status["recording_status"] == "recorded" and status["manifest"] == manifest


def test_rejected_retry_preserves_imported_fact(capture_env, av_file):
    from uuid import uuid4

    from materials_fixture import ORIGIN, PASSWORD

    from live_review.modules.identity.models import Admin
    from live_review.modules.identity.security import hasher

    fixture, settings, root = capture_env
    client, _, admin, _, _ = fixture
    run, _ = start_run(fixture)
    closed_fixture(root, run, av_file)
    run_job(app.state.engine, settings, run["job_id"], 1)
    endpoint = f"/api/v1/capture/runs/{run['capture_run_id']}"
    before = client.get(endpoint).json()
    assert before["state"] == "imported" and before["material_id"]
    with Session(app.state.engine) as db:
        alternate = Admin(
            workspace_id=admin.workspace_id,
            username=uuid4().hex,
            display_name="Authorized retry operator",
            password_hash=hasher.hash(PASSWORD),
        )
        username = alternate.username
        db.add(alternate)
        db.get(Admin, admin.id).active = False
        db.commit()
    login = client.post(
        "/api/v1/auth/login", headers=ORIGIN, json={"username": username, "password": PASSWORD}
    )
    headers = ORIGIN | {"X-CSRF-Token": login.json()["csrf_token"]}
    response = client.post(endpoint + "/import", headers=headers)
    assert response.status_code == 422 and response.json()["code"] == "actor_not_available"
    after = client.get(endpoint).json()
    assert after["state"] == "imported" and after["import_status"] == "imported"
    assert after["material_id"] == before["material_id"]
    assert after["error_code"] == "actor_not_available"

    # Simulate stage-result loss after material import committed, then retry as the worker.
    from datetime import timedelta
    from types import SimpleNamespace

    from live_review.integrations.capture.contracts import CaptureError
    from live_review.modules.capture.models import CaptureRun
    from live_review.modules.jobs.service import now
    from live_review.workers.capture_jobs import run_stage

    with Session(app.state.engine) as db:
        job = db.get(Job, UUID(run["job_id"]))
        data = job.input_data
        token = uuid4()
        job.lease_token, job.lease_until = token, now() + timedelta(seconds=60)
        db.commit()
    context = SimpleNamespace(
        engine=app.state.engine, job_id=UUID(run["job_id"]), input_data=lambda: data, token=token
    )
    with pytest.raises(CaptureError, match="actor_not_available"):
        run_stage(context, settings, "capture.import")
    with Session(app.state.engine) as db:
        row = db.get(CaptureRun, UUID(run["capture_run_id"]))
        assert row.state == "imported" and str(row.material_id) == before["material_id"]
        assert row.error_code == "actor_not_available"
