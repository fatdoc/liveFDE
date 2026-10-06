"""Real PostgreSQL authorization/revision/ownership; no real ASR provider calls."""

from datetime import timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from materials_fixture import ORIGIN, PASSWORD, upload, wav_bytes
from materials_fixture import materials as materials
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.main import app
from live_review.modules.jobs.execution import claim, recover_expired
from live_review.modules.jobs.models import Job, Outbox
from live_review.modules.jobs.service import now, stages_for


def configured(tmp_path, monkeypatch):
    src = Path(__file__).resolve().parents[3] / "config/asr.example.yaml"
    (tmp_path / "models.yaml").write_text(
        src.read_text().replace("enabled: false", "enabled: true")
    )
    monkeypatch.setattr(
        app.state,
        "settings",
        app.state.settings.model_copy(
            update={
                "model_config_dir": tmp_path,
                "asr_background_runner": False,
            }
        ),
    )


def test_settings_auth_csrf_persistence_revision_and_tenant(materials):
    client, headers, admin, _, stranger = materials
    endpoint = "/api/v1/asr/settings"
    before = client.get(endpoint).json()
    assert before["revision"] == 0 and before["privacy"] == "local_only"
    payload = {k: v for k, v in before.items() if k != "revision"}
    payload.update(expected_revision=0, speaker=True)
    assert client.put(endpoint, json=payload).status_code == 403
    first = client.put(endpoint, headers=headers, json=payload)
    assert first.status_code == 200 and first.json()["revision"] == 1
    assert client.put(endpoint, headers=headers, json=payload).status_code == 409
    invalid = payload | {"expected_revision": 1, "model_root": "/untrusted"}
    assert client.put(endpoint, headers=headers, json=invalid).status_code == 422
    with TestClient(app) as refresh:
        refresh.cookies.update(dict(client.cookies))
        assert refresh.get(endpoint).json()["speaker"]
    logged = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": stranger.username, "password": PASSWORD},
    )
    assert logged.status_code == 200
    assert client.get(endpoint).json()["revision"] == 0
    client.cookies.clear()
    assert client.get(endpoint).status_code == 401


def test_yaml_default_then_workspace_override(materials, tmp_path, monkeypatch):
    client, headers, _, _, _ = materials
    configured(tmp_path, monkeypatch)
    policy = tmp_path / "asr-policy.yaml"
    policy.write_text("defaults:\n  speaker: true\n")
    read = client.get("/api/v1/asr/settings").json()
    assert read["speaker"] and read["revision"] == 0
    saved = client.put(
        "/api/v1/asr/settings",
        headers=headers,
        json={k: v for k, v in read.items() if k != "revision"}
        | {"expected_revision": 0, "speaker": False},
    )
    assert saved.status_code == 200
    assert not client.get("/api/v1/asr/settings").json()["speaker"]


def test_file_submission_is_recorded_and_foreign_material_denied(materials, tmp_path, monkeypatch):
    client, headers, _, _, stranger = materials
    configured(tmp_path, monkeypatch)
    _, material = upload(client, headers, wav_bytes(), "audio/wav", "session_media")
    body = {"material_id": material["material_id"], "expected_revision": 0}
    unsaved = client.post("/api/v1/asr/transcriptions", headers=headers, json=body)
    assert unsaved.status_code == 409 and unsaved.json()["code"] == "settings_save_required"
    assert (
        client.put(
            "/api/v1/asr/settings", headers=headers, json={"expected_revision": 0}
        ).status_code
        == 200
    )
    body["expected_revision"] = 1
    created = client.post("/api/v1/asr/transcriptions", headers=headers, json=body)
    assert created.status_code == 202, created.text
    jid = UUID(created.json()["id"])
    with Session(app.state.engine) as db:
        job = db.get(Job, jid)
        assert job.input_data["authorization"]["allow_network"] is False
        assert job.input_data["gateway_policy_snapshot"]["content"]["schema_version"] == 1
        assert db.scalar(select(Outbox).where(Outbox.job_id == jid)) is not None
    assert client.get(f"/api/v1/asr/transcriptions/{jid}").json()["result"] is None
    logged = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": stranger.username, "password": PASSWORD},
    )
    other = ORIGIN | {"X-CSRF-Token": logged.json()["csrf_token"]}
    assert client.get(f"/api/v1/asr/transcriptions/{jid}").status_code == 404
    assert (
        client.put("/api/v1/asr/settings", headers=other, json={"expected_revision": 0}).status_code
        == 200
    )
    denied = client.post("/api/v1/asr/transcriptions", headers=other, json=body)
    assert denied.status_code == 422
    assert denied.json()["code"] == "material_not_available"


def test_local_submission_without_cloud_grant_ignores_disabled_fallback(
    materials, tmp_path, monkeypatch
):
    import yaml

    client, headers, _, _, _ = materials
    configured(tmp_path, monkeypatch)
    path = tmp_path / "models.yaml"
    config = yaml.safe_load(path.read_text())
    config["models"]["tencent_asr"]["route"]["enabled"] = False
    path.write_text(yaml.safe_dump(config))
    assert (
        client.put(
            "/api/v1/asr/settings",
            headers=headers,
            json={"expected_revision": 0, "privacy": "cloud_allowed", "allow_cloud_fallback": True},
        ).status_code
        == 200
    )
    _, material = upload(client, headers, wav_bytes(), "audio/wav", "session_media")
    reply = client.post(
        "/api/v1/asr/transcriptions",
        headers=headers,
        json={"material_id": material["material_id"], "expected_revision": 1},
    )
    assert reply.status_code == 202, reply.text


def test_direct_cloud_requires_per_task_budget_and_never_opens_client(
    materials, tmp_path, monkeypatch
):
    client, headers, _, _, _ = materials
    configured(tmp_path, monkeypatch)
    payload = {"expected_revision": 0, "provider": "tencent", "privacy": "cloud_allowed"}
    assert client.put("/api/v1/asr/settings", headers=headers, json=payload).status_code == 200
    _, material = upload(client, headers, wav_bytes(), "audio/wav", "session_media")
    import httpx

    # The HTTP request test client uses ASGI; construction below would mean provider network.
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected provider client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    reply = client.post(
        "/api/v1/asr/transcriptions",
        headers=headers,
        json={"expected_revision": 1, "material_id": material["material_id"]},
    )
    assert reply.status_code == 422 and reply.json()["code"] == "cloud_authorization_required"


def test_expired_stream_never_requeues(materials):
    from live_review.modules.jobs.service import create_job

    client, headers, admin, _, _ = materials
    with Session(app.state.engine, expire_on_commit=False) as db:
        job = create_job(
            db,
            admin.workspace_id,
            admin.id,
            [{"name": "asr", "handler": "asr.stream"}],
            {"kind": "asr_stream_v1"},
        )
        db.commit()
        jid = job.id
        before = len(db.scalars(select(Outbox).where(Outbox.job_id == jid)).all())
    claim(app.state.engine, jid, 1, 5)
    with Session(app.state.engine) as db:
        db.get(Job, jid).lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert recover_expired(app.state.engine) >= 1
    with Session(app.state.engine) as db:
        job = db.get(Job, jid)
        assert job.status == "failed" and job.error["code"] == "stream_not_replayable"
        assert len(db.scalars(select(Outbox).where(Outbox.job_id == jid)).all()) == before
        assert stages_for(db, jid)[0].status == "failed"
    assert not client.get(f"/api/v1/jobs/{jid}").json()["can_retry"]
