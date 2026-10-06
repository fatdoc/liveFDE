"""Native dispatch tests use isolated PG and local synthetic media, no platform calls."""

import base64
import json
import sys
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from capture_fixture import av_file as av_file
from capture_fixture import capture_env as capture_env
from capture_fixture import closed_fixture, start_run
from capture_fixture import materials as materials
from materials_fixture import ORIGIN, PASSWORD
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import load_policy
from live_review.main import app
from live_review.modules.capture.executor_health import binding, execution_health, paths
from live_review.modules.capture.files import exclusive
from live_review.modules.jobs.models import Job, Outbox
from live_review.modules.jobs.service import create_job, now
from live_review.workers.capture_executor import CaptureExecutor
from live_review.workers.dispatcher import dispatch_once


def native(settings):
    path = settings.model_config_dir / "capture.local.yaml"
    checkout = settings.model_config_dir / "synthetic-upstream"
    (checkout / "src").mkdir(parents=True, exist_ok=True)
    (checkout / "src/spider.py").touch()
    content = path.read_text()
    if "finder_executable:" not in content:
        content += f"finder_executable: {sys.executable}\n"
    path.write_text(content + f"execution_mode: native\n"
                    f"douyin_python: {sys.executable}\ndouyin_checkout: {checkout}\n")
    return load_policy(settings)


@contextmanager
def ready(settings, policy):
    lock, target = paths(policy)
    with exclusive(lock):
        target.write_text(
            json.dumps(
                {
                    "binding": binding(settings, policy),
                    "heartbeat_at": now().isoformat(),
                    "state": "idle",
                }
            )
        )
        yield target
    target.unlink(missing_ok=True)


def until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("condition did not become true")


def test_health_requires_matching_live_lock(capture_env):
    _, settings, _ = capture_env
    policy = native(settings)
    assert not execution_health(settings, policy)["ready"]
    with ready(settings, policy) as target:
        assert execution_health(settings, policy)["ready"]
        stamp = json.loads(target.read_text())
        for changes in (
            {"heartbeat_at": (now() - timedelta(seconds=11)).isoformat()},
            {"heartbeat_at": (now() + timedelta(seconds=60)).isoformat()},
            {"binding": "different_database_or_policy"},
            {"state": "draining"},
        ):
            target.write_text(json.dumps(stamp | changes))
            assert not execution_health(settings, policy)["ready"]
        target.write_text(json.dumps(stamp))
        assert not execution_health(settings, policy.model_copy(update={"max_seconds": 31}))[
            "ready"
        ]
    # Even a fresh matching heartbeat with no live process lock is unavailable.
    target.write_text(json.dumps(stamp))
    assert not execution_health(settings, policy)["ready"]
    target.unlink()
    target.symlink_to(target.parent / "missing")
    assert not execution_health(settings, policy)["ready"]


def test_native_start_gate_and_idempotent_retry(capture_env):
    fixture, settings, _ = capture_env
    client, headers, _, sessions, _ = fixture
    policy = native(settings)
    data = {"session_id": str(sessions[0].id), "platform": "wechat", "source_ref": "phone_cast"}
    endpoint = "/api/v1/capture/runs"
    request_headers = headers | {"Idempotency-Key": "native"}
    assert client.post(endpoint, headers=request_headers, json=data).status_code == 503
    with ready(settings, policy):
        run, data = start_run(fixture, "wechat", "native")
        health = client.get("/api/v1/capture/health").json()
        assert health["execution"]["automatic_dispatch"] and health["execution"]["ready"]
    again = client.post(endpoint, headers=request_headers, json=data)
    assert again.status_code == 202 and again.json()["capture_run_id"] == run["capture_run_id"]


def test_run_list_restores_pages_and_workspace_isolation(capture_env):
    fixture, _, _ = capture_env
    client, headers, _, sessions, stranger = fixture
    ids = []
    for i in range(3):
        run, _ = start_run(fixture, key=f"list-{i}")
        ids.append(run["capture_run_id"])
        with Session(app.state.engine) as db:
            db.get(Job, UUID(run["job_id"])).status = "failed"
            db.commit()
    endpoint = f"/api/v1/capture/runs?session_id={sessions[0].id}&limit=2"
    first = client.get(endpoint).json()
    assert [r["capture_run_id"] for r in first["items"]] == ids[::-1][:2]
    assert all(r["created_at"] for r in first["items"])
    second_response = client.get(
        "/api/v1/capture/runs",
        params={"session_id": str(sessions[0].id), "limit": 2, "cursor": first["next_cursor"]},
    )
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert [r["capture_run_id"] for r in second["items"]] == ids[:1]
    assert second["next_cursor"] is None
    invalid = client.get(
        "/api/v1/capture/runs",
        params={"session_id": str(sessions[0].id), "cursor": "invalid"},
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_cursor"
    valid = {"session_id": str(sessions[0].id), "created_at": now().isoformat(), "id": ids[0]}
    for payload in (
        [],
        None,
        {},
        valid | {"id": 123},
        valid | {"id": {}},
        valid | {"created_at": 123},
        valid | {"session_id": None},
        valid | {"created_at": "2026-10-06T00:00:00"},
        valid | {"session_id": str(sessions[1].id)},
    ):
        cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        malformed = client.get(
            "/api/v1/capture/runs", params={"session_id": str(sessions[0].id), "cursor": cursor}
        )
        assert malformed.status_code == 422 and malformed.json()["code"] == "invalid_cursor"
    assert client.get(endpoint.replace("limit=2", "limit=101")).status_code == 422
    client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": stranger.username, "password": PASSWORD},
    )
    assert client.get(endpoint).status_code == 404


def test_native_dispatch_imports_and_leaves_other_jobs_untouched(capture_env, av_file):
    fixture, settings, root = capture_env
    client, _, admin, _, _ = fixture
    policy = native(settings)
    with ready(settings, policy):
        run, _ = start_run(fixture)
    closed_fixture(root, run, av_file)
    with Session(app.state.engine) as db:
        unrelated = create_job(
            db,
            admin.workspace_id,
            admin.id,
            [{"name": "other", "handler": "fixture.noop"}],
            {"kind": "unrelated"},
        )
        unrelated.status = "running"
        unrelated.lease_token, unrelated.lease_until = uuid4(), now() - timedelta(seconds=5)
        other_id, lease = unrelated.id, unrelated.lease_token
        db.commit()
    CaptureExecutor(app.state.engine, settings).run(once=True)
    result = client.get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()
    assert result["state"] == "imported" and result["material_id"]
    with Session(app.state.engine) as db:
        assert db.get(Job, other_id).lease_token == lease
        assert db.get(Job, other_id).status == "running"
        assert db.scalar(select(Outbox).where(Outbox.job_id == other_id)).status == "pending"
        assert (
            db.scalar(select(Outbox).where(Outbox.job_id == UUID(run["job_id"]))).status == "sent"
        )
    assert not execution_health(settings, policy)["ready"]
    assert not dispatch_once(
        app.state.engine,
        settings,
        kind="capture_v1",
        publisher=lambda *_: pytest.fail("duplicate work"),
    )


def test_native_heartbeat_busy_shutdown_and_singleton(capture_env, monkeypatch):
    fixture, settings, _ = capture_env
    client, _, _, _, _ = fixture
    policy = native(settings)
    executor = CaptureExecutor(app.state.engine, settings)
    entered, release = threading.Event(), threading.Event()

    def hold(*_):
        entered.set()
        assert release.wait(15)

    monkeypatch.setattr("live_review.workers.capture_executor.run_job", hold)
    worker = threading.Thread(target=executor.run)
    worker.start()
    try:
        until(lambda: execution_health(settings, policy)["ready"])
        run, _ = start_run(fixture)
        assert entered.wait(5)
        until(lambda: execution_health(settings, policy)["state"] == "busy")
        with pytest.raises(CaptureError, match="capture_busy"):
            CaptureExecutor(app.state.engine, settings).run(once=True)
        executor.request_shutdown()
        until(lambda: execution_health(settings, policy)["state"] == "draining")
        assert not execution_health(settings, policy)["ready"]
        until(
            lambda: client.get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()[
                "stop_requested"
            ]
        )
    finally:
        release.set()
        executor.request_shutdown()
        worker.join(10)
    assert not worker.is_alive() and not execution_health(settings, policy)["ready"]


@pytest.mark.parametrize("shutdown", ["terminate", "kill"])
def test_native_process_shutdown_closes_receiver(capture_env, tmp_path, shutdown):
    import os
    import subprocess
    import sys

    fixture, settings, _ = capture_env
    client, _, _, _, _ = fixture
    receiver_pid = tmp_path / "receiver.pid"
    helper = tmp_path / "synthetic-receiver"
    helper.write_text(
        f"#!{sys.executable}\nimport os,time\nfrom pathlib import Path\n"
        f"Path({str(receiver_pid)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n"
    )
    helper.chmod(0o700)
    config = settings.model_config_dir / "capture.local.yaml"
    config.write_text(config.read_text() + f"finder_executable: {helper}\n")
    policy = native(settings)
    environment = os.environ | {
        "LIVE_DATABASE_URL": settings.database_url.get_secret_value(),
        "LIVE_MODEL_CONFIG_DIR": str(settings.model_config_dir),
        "LIVE_JOB_DISPATCH_INTERVAL_SECONDS": "0.1",
        "LIVE_JOB_LEASE_SECONDS": "3",
    }
    worker = subprocess.Popen(
        [sys.executable, "-m", "live_review.workers.capture_executor"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        until(lambda: execution_health(settings, policy)["ready"])
        run, _ = start_run(fixture, "wechat")
        until(receiver_pid.exists)
        pid = int(receiver_pid.read_text())
        getattr(worker, shutdown)()
        worker.wait(timeout=15)

        def gone():
            try:
                os.kill(pid, 0)
                return False
            except ProcessLookupError:
                return True

        until(gone)
        assert not execution_health(settings, policy)["ready"]
        if shutdown == "terminate":
            result = client.get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()
            assert result["state"] == "stopped" and result["material_id"] is None
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)


def test_browser_queue_to_actual_media_and_import(capture_env, av_file, monkeypatch):
    """Actual FFmpeg/data flow; invoke handlers in-process only to inject local source.

    Independent subprocess lifetime is covered by the shutdown tests above.
    This fixture does not enable any local-address exception in product policy.
    """
    import subprocess

    from test_capture_recording import http_source, permit_fixture

    from live_review.integrations.capture import recording, relay
    from live_review.integrations.capture.contracts import Source
    from live_review.workers import capture_jobs, job_runner

    fixture, settings, _ = capture_env
    client, headers, _, _, _ = fixture
    policy = native(settings)
    monkeypatch.setattr(relay, "destination", permit_fixture)
    monkeypatch.setattr(
        job_runner,
        "execute_handler",
        lambda context, settings, handler: capture_jobs.run_stage(context, settings, handler),
    )
    original = subprocess.Popen

    def paced(command, **kwargs):
        if command[0] == "ffmpeg" and "-progress" in command:
            index = command.index("-i")
            command = command[:index] + ["-re"] + command[index:]
        return original(command, **kwargs)

    monkeypatch.setattr(recording.subprocess, "Popen", paced)
    with http_source(av_file) as url:

        class LocalSource:
            def health(self):
                return {"dependencies_ready": True, "real_platform_verified": False}

            def acquire(self, reference, tick):
                tick()
                return Source(True, url)

        monkeypatch.setattr(capture_jobs.CaptureRegistry, "get", lambda *_: LocalSource())
        executor = CaptureExecutor(app.state.engine, settings)
        worker = threading.Thread(target=executor.run)
        worker.start()
        try:
            until(lambda: execution_health(settings, policy)["ready"])
            run, _ = start_run(fixture, "wechat")
            endpoint = f"/api/v1/capture/runs/{run['capture_run_id']}"
            until(lambda: client.get(endpoint).json()["state"] == "recording")
            assert client.post(endpoint + "/stop", headers=headers).status_code == 202
            until(lambda: client.get(endpoint).json()["state"] == "imported")
            result = client.get(endpoint).json()
            assert result["manifest"]["closed"] and result["manifest"]["end_reason"] == "user_stop"
            assert {"audio", "video"} <= set(result["manifest"]["media_types"])
            assert result["transcription_status"] == "not_requested"
            assert (
                client.get(f"/api/v1/materials/{result['material_id']}/content").status_code == 200
            )
        finally:
            executor.request_shutdown()
            worker.join(15)
        assert not worker.is_alive()


def test_database_failure_withdraws_ready_and_releases_lock(capture_env, monkeypatch):
    _, settings, _ = capture_env
    policy = native(settings)
    executor = CaptureExecutor(app.state.engine, settings)
    lock, target = paths(policy)
    with exclusive(lock):
        executor._heartbeat()
        assert execution_health(settings, policy)["ready"]

        def disconnected():
            executor.finished.set()
            raise RuntimeError("synthetic_database_disconnect")

        with monkeypatch.context() as patch:
            patch.setattr(app.state.engine, "connect", disconnected)
            executor._pulse()
        assert not target.exists() and not execution_health(settings, policy)["ready"]

    def dispatch_failure(*args, **kwargs):
        raise RuntimeError("synthetic_dispatch_database_disconnect")

    monkeypatch.setattr("live_review.workers.capture_executor.dispatch_once", dispatch_failure)
    with pytest.raises(RuntimeError, match="synthetic_dispatch_database_disconnect"):
        CaptureExecutor(app.state.engine, settings).run(once=True)
    assert not target.exists()
    with exclusive(lock):
        pass
