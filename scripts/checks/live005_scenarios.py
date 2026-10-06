"""Actual isolated services, additive migrations, and synthetic job fault scenarios."""

import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from live005_smoke import ORIGIN, ROOT, RUNTIME
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


def require(response, status=200):
    assert response.status_code == status, (response.status_code, response.text[:250])
    return response.json()


def login(h, label):
    username, password = "synthetic-" + uuid4().hex, secrets.token_hex(24)
    h.command(
        "-m",
        "live_review.modules.identity.cli",
        "--username",
        username,
        "--display-name",
        label,
        "--workspace-name",
        label,
        "--password-stdin",
        input=password + "\n",
    )
    data = require(
        h.client.post(
            "/api/v1/auth/login", headers=ORIGIN, json={"username": username, "password": password}
        )
    )
    return data["user"], ORIGIN | {"X-CSRF-Token": data["csrf_token"]}


def preserve_004(h, engine):
    with engine.connect() as db:
        exists = db.scalar(text("SELECT to_regclass('public.alembic_version')"))
        previous = db.scalar(text("SELECT version_num FROM alembic_version")) if exists else None
    fresh = previous is None
    h.command("-m", "alembic", "upgrade", "0003_materials" if fresh else "head")
    h.start_api()
    user, headers = login(h, "Synthetic upgrade witness")
    streamer = require(
        h.client.post(
            "/api/v1/streamers", headers=headers, json={"name": "Synthetic", "platform": "other"}
        ),
        201,
    )
    session = require(
        h.client.post(
            "/api/v1/sessions",
            headers=headers,
            json={
                "streamer_id": streamer["id"],
                "title": "Synthetic migration witness",
                "platform": "other",
                "session_local_date": "2026-10-05",
                "started_at": None,
                "time_precision": "date",
            },
        ),
        201,
    )
    body = b"Synthetic pre-migration transcript\n"
    uploaded = require(
        h.client.post(
            "/api/v1/materials/uploads",
            headers=headers | {"Idempotency-Key": uuid4().hex},
            json={
                "filename": "witness.txt",
                "byte_size": len(body),
                "media_type": "text/plain",
                "purpose": "transcript",
            },
        ),
        201,
    )
    require(
        h.client.put(
            f"/api/v1/materials/uploads/{uploaded['upload_id']}/content",
            headers=headers,
            content=body,
        )
    )
    material = require(
        h.client.post(
            f"/api/v1/materials/uploads/{uploaded['upload_id']}/finalize", headers=headers
        )
    )
    require(
        h.client.post(
            f"/api/v1/sessions/{session['id']}/materials",
            headers=headers,
            json={"material_id": material["material_id"], "role": "primary"},
        ),
        201,
    )
    h.stop(h.api)
    h.command("-m", "alembic", "upgrade", "head")
    h.command("-m", "alembic", "check")
    h.start_api()
    assert require(h.client.get("/api/v1/auth/me"))["user"]["id"] == user["id"]
    assert require(h.client.get(f"/api/v1/sessions/{session['id']}"))["id"] == session["id"]
    original = h.client.get(f"/api/v1/materials/{material['material_id']}/content")
    assert original.status_code == 200 and original.content == body
    assert hashlib.sha256(original.content).hexdigest() == material["sha256"]
    linked = require(h.client.get(f"/api/v1/sessions/{session['id']}/materials"))
    assert linked["total"] == 1
    h.results["fresh_004_to_005_upgrade"] = fresh
    h.results["preserved_material_sha256"] = material["sha256"]
    if fresh:
        (RUNTIME / "fresh-upgrade-results.json").write_text(json.dumps(h.results, indent=2) + "\n")
    h.record("004 identity session and original material bytes survive additive 005 migration")
    return user, headers


def run_scenarios(h):
    from live_review.modules.jobs.models import CallIntent, Job, JobStage, Outbox
    from live_review.modules.jobs.service import create_job

    engine = create_engine(h.env["LIVE_DATABASE_URL"])
    user, headers = preserve_004(h, engine)

    def create(handlers, **inputs):
        with Session(engine) as db:
            job = create_job(
                db,
                UUID(user["workspace_id"]),
                UUID(user["id"]),
                [{"name": f"step{i}", "handler": name} for i, name in enumerate(handlers)],
                inputs,
            )
            identifier = job.id
            db.commit()
        return str(identifier)

    def view(identifier):
        return require(h.client.get("/api/v1/jobs/" + identifier))

    def wait(identifier, status):
        return h.until(
            lambda: value if (value := view(identifier))["status"] == status else None,
            f"{identifier}: {status}",
            40,
        )

    def worker(label):
        return h.start(
            label,
            "-m",
            "celery",
            "-A",
            "live_review.workers.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=WARNING",
            "--hostname",
            label + "@live005",
            "--without-gossip",
            "--without-mingle",
        )

    def dispatch():
        # Preserve previous synthetic evidence; drain eligible outbox rows rather
        # than assuming a pristine database after an interrupted acceptance run.
        for _ in range(30):
            h.command("-m", "live_review.workers.dispatcher", "--once")
            with Session(engine) as db:
                pending = db.scalar(
                    select(Outbox.id)
                    .where(Outbox.status == "pending", Outbox.next_attempt_at <= datetime.now(UTC))
                    .limit(1)
                )
            if pending is None:
                return
        raise AssertionError("Outbox did not drain within the bounded acceptance window")

    def artifacts(identifier):
        with Session(engine) as db:
            return [
                (row.name, row.artifact, row.completed_attempt)
                for row in db.scalars(
                    select(JobStage)
                    .where(JobStage.job_id == UUID(identifier))
                    .order_by(JobStage.ordinal)
                )
            ]

    def broker(action):
        result = subprocess.run(
            [sys_python(), str(ROOT / "scripts/checks/live005_environment.py"), action],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        (RUNTIME / (action + "-control.log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, "Broker control failed; private runtime log retained"

    # No business/API creation endpoint is invented: caller's PG transaction owns creation.
    with Session(engine) as db:
        row = create_job(
            db,
            UUID(user["workspace_id"]),
            UUID(user["id"]),
            [{"name": "rollback", "handler": "fixture.echo"}],
            {},
        )
        rolled_back = row.id
        db.rollback()
    with Session(engine) as db:
        assert db.get(Job, rolled_back) is None
        assert not db.scalar(select(Outbox.id).where(Outbox.job_id == rolled_back))
    h.record("business transaction rollback leaves neither job nor outbox")

    identifier = create(["fixture.echo"], value="broker-durable")
    broker("mq-stop")
    try:
        dispatch()
        with Session(engine) as db:
            event = db.scalar(select(Outbox).where(Outbox.job_id == UUID(identifier)))
            assert event.status == "pending" and event.delivery_attempts >= 1
    finally:
        broker("mq-start")
    time.sleep(2.1)
    dispatch()
    # Confirmed durable message must survive broker restart before any worker is started.
    broker("mq-restart")
    current_worker = worker("005-worker-one")
    wait(identifier, "succeeded")
    snapshot = artifacts(identifier)
    snapshot_state = view(identifier)
    assert snapshot[0][1]["value"] == "broker-durable"
    h.record("broker unavailable keeps outbox; persistent confirmed message survives restart")

    gap = create(["fixture.echo"], value="confirmed-before-commit")
    dying = h.start(
        "dispatch-crash",
        "-c",
        """
import os
from live_review.core.config import get_settings
from live_review.core.database import build_engine
from live_review.workers.dispatcher import dispatch_once, publish
settings = get_settings()
def confirmed_then_die(event, settings):
    publish(event, settings)
    os._exit(17)
dispatch_once(build_engine(settings), settings, confirmed_then_die)
""",
    )
    assert dying.wait(timeout=20) == 17
    wait(gap, "succeeded")
    gap_snapshot = artifacts(gap)
    gap_state = view(gap)
    with Session(engine) as db:
        event = db.scalar(select(Outbox).where(Outbox.job_id == UUID(gap)))
        assert event.status == "pending" and event.sent_at is None
    dispatch()
    h.record("dispatcher killed after broker confirm retains pending outbox for safe replay")

    # Replay same message several times, then restart worker and replay again.
    from live_review.workers.celery_app import celery_app

    for _ in range(3):
        celery_app.send_task("live_review.run_job", args=[identifier, 1])
    h.stop(current_worker)
    current_worker = worker("005-worker-two")
    sentinel = create(["fixture.echo"], value="queue-drained")
    dispatch()
    wait(sentinel, "succeeded")
    assert artifacts(identifier) == snapshot
    assert artifacts(gap) == gap_snapshot
    assert view(identifier) == snapshot_state and view(gap) == gap_state
    h.record("duplicate delivery and worker restart cannot duplicate committed stage artifacts")

    failed = create(["fixture.echo", "fixture.fail_once"], value="keep-stage-zero")
    dispatch()
    failure = wait(failed, "failed")
    assert failure["can_retry"] and failure["error"]["code"] == "stage_failed"
    assert "synthetic first-attempt" not in json.dumps(failure)
    prior_stage = artifacts(failed)[0]
    retry_body = {"expected_revision": failure["revision"], "from_stage": "step1"}
    retry_headers = headers | {"Idempotency-Key": uuid4().hex}
    first = require(
        h.client.post("/api/v1/jobs/" + failed + "/retry", headers=retry_headers, json=retry_body),
        202,
    )
    assert (
        require(
            h.client.post(
                "/api/v1/jobs/" + failed + "/retry", headers=retry_headers, json=retry_body
            ),
            202,
        )
        == first
    )
    assert (
        h.client.post(
            "/api/v1/jobs/" + failed + "/retry",
            headers=retry_headers,
            json=retry_body | {"from_stage": "step0"},
        ).status_code
        == 409
    )
    celery_app.send_task("live_review.run_job", args=[failed, 1])  # delayed old attempt
    dispatch()
    retried = wait(failed, "succeeded")
    assert retried["attempt"] == 2
    assert retried["attempt_history"][0]["error"]["code"] == "stage_failed"
    assert artifacts(failed)[0] == prior_stage
    h.record("failed-stage retry retains prior output; request replay and old messages are safe")

    def handler_pid(identifier, label):
        log = RUNTIME / (label + ".log")

        def started():
            match = re.search(
                r"handler_started job=" + identifier + r" pid=(\d+)",
                log.read_text(errors="replace"),
            )
            return int(match.group(1)) if match else None

        return h.until(started, "handler process started")

    # Kill only parent worker PID, not its process group, to test orphan handling.
    interrupted = create(["fixture.uncooperative"], delay_seconds=12)
    dispatch()
    orphan_pid = handler_pid(interrupted, "005-worker-two")
    wait(interrupted, "running")
    os.kill(current_worker.pid, signal.SIGKILL)
    current_worker.wait(timeout=5)

    def orphan_stopped():
        try:
            os.kill(orphan_pid, 0)
            return False
        except ProcessLookupError:
            return True

    h.until(orphan_stopped, "orphan watchdog stops before natural handler completion", timeout=3)
    time.sleep(4.5)
    dispatch()
    current_worker = worker("005-worker-three")
    wait(interrupted, "succeeded")
    h.record("abrupt worker death recovers durable job through expired lease")

    fenced = create(["fixture.slow"], delay_seconds=2)
    dispatch()
    handler_pid(fenced, "005-worker-three")
    paused = current_worker
    os.killpg(paused.pid, signal.SIGSTOP)
    try:
        time.sleep(4.5)
        dispatch()
        current_worker = worker("005-worker-fenced")
        wait(fenced, "succeeded")
        fenced_snapshot = artifacts(fenced)
    finally:
        os.killpg(paused.pid, signal.SIGCONT)
    h.until(
        lambda: (
            "handler_stopped job=" + fenced
            in (RUNTIME / "005-worker-three.log").read_text(errors="replace")
        ),
        "old handler stopped",
    )
    h.stop(paused)
    assert artifacts(fenced) == fenced_snapshot
    h.record("paused old worker resumes after new lease success and cannot overwrite artifact")

    canceled = create(["fixture.uncooperative"], delay_seconds=30)
    dispatch()
    child_pid = handler_pid(canceled, "005-worker-fenced")
    state = wait(canceled, "running")
    cancel = h.client.post(
        "/api/v1/jobs/" + canceled + "/cancel",
        headers=headers,
        json={"expected_revision": state["revision"]},
    )
    if cancel.status_code == 409:
        state = view(canceled)
        cancel = h.client.post(
            "/api/v1/jobs/" + canceled + "/cancel",
            headers=headers,
            json={"expected_revision": state["revision"]},
        )
    assert cancel.status_code == 202 and cancel.json()["cancel_requested"]
    wait(canceled, "canceled")
    try:
        os.kill(child_pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("Canceled handler process is still alive")
    assert artifacts(canceled)[0][1] is None
    assert (
        h.client.post(
            "/api/v1/jobs/" + canceled + "/cancel", headers=headers, json={"expected_revision": 1}
        ).status_code
        == 200
    )
    h.record("cancel request remains distinct from worker confirmed stop; no result committed")

    unknown = create(["fixture.paid_unknown"], delay_seconds=30)
    dispatch()
    wait(unknown, "running")

    def has_intent():
        with Session(engine) as db:
            return bool(db.scalar(select(CallIntent.id).where(CallIntent.job_id == UUID(unknown))))

    h.until(has_intent, "durable synthetic call intent")
    os.kill(current_worker.pid, signal.SIGKILL)
    current_worker.wait(timeout=5)
    time.sleep(4.5)
    dispatch()
    unsafe = wait(unknown, "failed")
    assert not unsafe["can_retry"] and unsafe["error"]["code"] == "call_result_unknown"
    assert (
        h.client.post(
            "/api/v1/jobs/" + unknown + "/retry",
            headers=headers | {"Idempotency-Key": uuid4().hex},
            json={"expected_revision": unsafe["revision"], "from_stage": "step0"},
        ).status_code
        == 409
    )
    current_worker = worker("005-worker-four")
    celery_app.send_task("live_review.run_job", args=[unknown, 1])
    sentinel = create(["fixture.echo"])
    dispatch()
    wait(sentinel, "succeeded")
    with Session(engine) as db:
        calls = db.scalars(select(CallIntent).where(CallIntent.job_id == UUID(unknown))).all()
        assert len(calls) == 1
    h.record("unknown synthetic paid-call intent survives kill and blocks every automatic replay")

    h.stop(h.api)
    h.start_api()
    assert view(identifier)["status"] == "succeeded"
    assert artifacts(identifier) == snapshot
    assert (
        h.client.post(
            "/api/v1/jobs/" + identifier + "/cancel", json={"expected_revision": 1}
        ).status_code
        == 403
    )
    with httpx.Client(base_url=h.client.base_url, trust_env=False) as anonymous:
        assert anonymous.get("/api/v1/jobs/" + identifier).status_code == 401
    _, second_headers = login(h, "Synthetic other workspace")
    assert h.client.get("/api/v1/jobs/" + identifier).status_code == 404
    assert (
        h.client.post(
            "/api/v1/jobs/" + identifier + "/cancel",
            headers=second_headers,
            json={"expected_revision": 1},
        ).status_code
        == 404
    )
    h.record("API restart retains state; authentication CSRF and workspace boundaries enforced")
    h.stop(current_worker)
    engine.dispose()


def sys_python():
    import sys

    return sys.executable
