from datetime import timedelta
from uuid import UUID

import pytest
from capture_fixture import av_file as av_file
from capture_fixture import capture_env as capture_env
from capture_fixture import materials as materials
from capture_fixture import start_run
from materials_fixture import ORIGIN, PASSWORD
from sqlalchemy.orm import Session

from live_review.main import app
from live_review.modules.jobs.execution import claim, recover_expired
from live_review.modules.jobs.models import Job
from live_review.modules.jobs.service import now
from live_review.workers.job_runner import run_job


def test_auth_invalid_duplicate_and_stop(capture_env):
    fixture, settings, _ = capture_env
    client, headers, _, _, stranger = fixture
    run, data = start_run(fixture)
    endpoint = "/api/v1/capture/runs"
    same = client.post(endpoint, json=data, headers=headers | {"Idempotency-Key": "capture-test"})
    assert same.json()["capture_run_id"] == run["capture_run_id"]
    assert (
        client.post(
            endpoint, json=data, headers=headers | {"Idempotency-Key": "different"}
        ).status_code
        == 409
    )
    assert client.post(endpoint, json=data, headers={"Idempotency-Key": "x"}).status_code == 403
    for reference in (
        "https://evil.example/1",
        "file:///etc/passwd",
        "https://live.douyin.com/1?token=secret",
    ):
        assert (
            client.post(
                endpoint,
                json=data | {"source_ref": reference},
                headers=headers | {"Idempotency-Key": "x"},
            ).status_code
            == 422
        )
    path = endpoint + "/" + run["capture_run_id"]
    stop = client.post(path + "/stop", headers=headers)
    assert stop.status_code == 202 and stop.json()["state"] == "queued"
    run_job(app.state.engine, settings, run["job_id"], 1)
    state = client.get(path).json()
    assert state["state"] == "stopped" and state["material_id"] is None
    client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": stranger.username, "password": PASSWORD},
    )
    assert client.get(path).status_code == 404
    client.cookies.clear()
    assert client.get("/api/v1/capture/health").status_code == 401


def test_cancel_before_start_and_restart_marker(capture_env):
    fixture, settings, root = capture_env
    client, headers, _, _, _ = fixture
    run, _ = start_run(fixture)
    response = client.post(
        f"/api/v1/jobs/{run['job_id']}/cancel", headers=headers, json={"expected_revision": 1}
    )
    assert response.status_code == 202
    run_job(app.state.engine, settings, run["job_id"], 1)
    assert client.get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()["state"] == "canceled"
    run, _ = start_run(fixture, key="restart")
    path = root / run["capture_run_id"]
    path.mkdir()
    (path / "started.json").write_text("{}")
    job_id = UUID(run["job_id"])
    assert claim(app.state.engine, job_id, 1, 30)
    with Session(app.state.engine) as db:
        job = db.get(Job, job_id)
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    assert recover_expired(app.state.engine) >= 1
    run_job(app.state.engine, settings, job_id, 1)
    state = client.get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()
    assert state["error_code"] == "restart_interrupted"
    assert state["material_id"] is None


def test_provider_offline_is_not_parse_failure(capture_env, monkeypatch):
    import pytest
    from sqlalchemy import select

    from live_review.integrations.capture.contracts import CaptureError, Source
    from live_review.modules.capture.models import CaptureRun
    from live_review.modules.jobs.execution import Context
    from live_review.modules.jobs.models import JobStage
    from live_review.workers import capture_jobs

    fixture, settings, _ = capture_env
    run, _ = start_run(fixture)
    job_id = UUID(run["job_id"])
    token = claim(app.state.engine, job_id, 1, 30)
    with Session(app.state.engine) as db:
        stage = db.scalar(
            select(JobStage).where(JobStage.job_id == job_id, JobStage.name == "record")
        )
        stage_id = stage.id
    provider = type("Offline", (), {"acquire": lambda *a: Source(False)})()
    monkeypatch.setattr(
        capture_jobs, "CaptureRegistry", lambda _: type("R", (), {"get": lambda *a: provider})()
    )
    with pytest.raises(CaptureError, match="not_live"):
        capture_jobs.run_stage(
            Context(app.state.engine, job_id, token, stage_id, 30), settings, "capture.record"
        )
    with Session(app.state.engine) as db:
        assert db.get(CaptureRun, UUID(run["capture_run_id"])).error_code == "not_live"


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_running_receiver_process_stops(capture_env, tmp_path, action):
    import os
    import sys
    import threading
    import time

    import yaml

    fixture, settings, _ = capture_env
    client, headers, _, _, _ = fixture
    executable = tmp_path / "waiting-receiver"
    pid_file = tmp_path / "receiver.pid"
    executable.write_text(
        f"#!{sys.executable}\nimport os,time,pathlib\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    executable.chmod(0o700)
    policy_file = settings.model_config_dir / "capture.local.yaml"
    values = yaml.safe_load(policy_file.read_text())
    values["finder_executable"] = str(executable)
    policy_file.write_text(yaml.safe_dump(values))
    run, _ = start_run(fixture, platform="wechat")
    thread = threading.Thread(target=run_job, args=(app.state.engine, settings, run["job_id"], 1))
    thread.start()
    deadline = time.monotonic() + 15
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert pid_file.exists()
    pid = int(pid_file.read_text())
    endpoint = f"/api/v1/capture/runs/{run['capture_run_id']}"
    assert client.get(endpoint).json()["state"] == "waiting_for_cast"
    if action == "stop":
        assert client.post(endpoint + "/stop", headers=headers).status_code == 202
    else:
        job = client.get(f"/api/v1/jobs/{run['job_id']}").json()
        assert (
            client.post(
                f"/api/v1/jobs/{run['job_id']}/cancel",
                headers=headers,
                json={"expected_revision": job["revision"]},
            ).status_code
            == 202
        )
    thread.join(timeout=15)
    assert not thread.is_alive()
    state = client.get(endpoint).json()
    assert state["state"] == ("stopped" if action == "stop" else "canceled")
    assert state["material_id"] is None
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_wechat_wait_url_record_import_states(capture_env, av_file, monkeypatch):
    import subprocess

    from sqlalchemy import select
    from test_capture_recording import http_source, permit_fixture

    from live_review.integrations.capture import recording, relay
    from live_review.integrations.capture.contracts import Source
    from live_review.modules.capture.models import CaptureRun
    from live_review.modules.jobs.execution import Context
    from live_review.modules.jobs.models import JobStage
    from live_review.workers import capture_jobs

    fixture, settings, _ = capture_env
    client, headers, _, _, _ = fixture
    run, _ = start_run(fixture, platform="wechat")
    run_id, job_id = UUID(run["capture_run_id"]), UUID(run["job_id"])
    token = claim(app.state.engine, job_id, 1, 30)
    with Session(app.state.engine) as db:
        stage = db.scalar(
            select(JobStage).where(JobStage.job_id == job_id, JobStage.name == "record")
        )
        context = Context(app.state.engine, job_id, token, stage.id, 30)
    observed = []

    def state():
        with Session(app.state.engine) as db:
            return db.get(CaptureRun, run_id).state

    original_record = recording.record

    def checked_record(source, path, policy, tick, progress, *args):
        observed.append(state())

        def progress_and_stop(value):
            progress(value)
            observed.append(state())
            assert (
                client.post(f"/api/v1/capture/runs/{run_id}/stop", headers=headers).status_code
                == 202
            )

        return original_record(source, path, policy, tick, progress_and_stop, *args)

    monkeypatch.setattr(capture_jobs, "record", checked_record)
    monkeypatch.setattr(relay, "destination", permit_fixture)
    original_popen = subprocess.Popen

    def paced(command, **kwargs):
        if command[0] == "ffmpeg" and "-progress" in command:
            index = command.index("-i")
            command = command[:index] + ["-re"] + command[index:]
        return original_popen(command, **kwargs)

    monkeypatch.setattr(recording.subprocess, "Popen", paced)
    with http_source(av_file) as url:

        class Phone:
            def acquire(self, reference, tick):
                tick()
                observed.append(state())
                return Source(True, url)

        monkeypatch.setattr(
            capture_jobs, "CaptureRegistry", lambda _: type("R", (), {"get": lambda *a: Phone()})()
        )
        capture_jobs.run_stage(context, settings, "capture.record")
    assert observed == ["waiting_for_cast", "url_received", "recording"]
    assert state() == "recorded"
    result = capture_jobs.run_stage(context, settings, "capture.import")
    assert result["material_id"] and state() == "imported"
