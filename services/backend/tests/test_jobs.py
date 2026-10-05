from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from jobs_fixture import jobs as jobs
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from live_review.modules.jobs.execution import Context, LostLease, claim, locked, recover_expired
from live_review.modules.jobs.models import Job, Outbox
from live_review.modules.jobs.service import create_job, now, stages_for
from live_review.workers.dispatcher import dispatch_once
from live_review.workers.job_runner import run_job


def test_creation_is_atomic_and_actor_scoped(jobs):
    _, _, admin, _, engine, _ = jobs
    with Session(engine) as db:
        job = create_job(
            db, admin.workspace_id, admin.id, [{"name": "a", "handler": "fixture.echo"}], {}
        )
        uid = job.id
        db.rollback()
        assert db.get(Job, uid) is None
        assert db.scalar(select(func.count()).select_from(Outbox).where(Outbox.job_id == uid)) == 0
        with pytest.raises(ValueError):
            create_job(db, uuid4(), admin.id, [{"name": "a", "handler": "fixture.echo"}], {})


def test_worker_duplicate_and_artifact_atomicity(jobs):
    client, _, _, make, engine, settings = jobs
    uid = make()
    run_job(engine, settings, uid, 1)
    result = client.get(f"/api/v1/jobs/{uid}").json()
    assert result["status"] == "succeeded" and result["progress"] is None
    run_job(engine, settings, uid, 1)
    assert client.get(f"/api/v1/jobs/{uid}").json() == result
    with Session(engine) as db:
        stage = stages_for(db, uid)[0]
        assert stage.artifact == {"synthetic": True, "value": "synthetic"}
        assert stage.completed_attempt == 1


def test_failure_retry_preserves_prior_stage_and_idempotency(jobs):
    client, headers, _, make, engine, settings = jobs
    uid = make(["fixture.echo", "fixture.fail_once"])
    run_job(engine, settings, uid, 1)
    failed = client.get(f"/api/v1/jobs/{uid}").json()
    assert failed["status"] == "failed" and failed["can_retry"]
    assert "synthetic first" not in str(failed)
    body = {"expected_revision": failed["revision"], "from_stage": "stage1"}
    key = headers | {"Idempotency-Key": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(f"/api/v1/jobs/{uid}/retry", headers=key, json=body), range(2)
            )
        )
    assert all(response.status_code == 202 for response in responses)
    assert responses[0].json() == responses[1].json()
    history = responses[0].json()["attempt_history"]
    assert len(history) == 1 and history[0]["attempt"] == 1
    assert history[0]["error"] == failed["error"]
    assert history[0]["steps"][0]["artifact"] == {"synthetic": True, "value": "synthetic"}
    assert history[0]["steps"][1]["reason"] == "stage_failed"
    assert (
        client.post(
            f"/api/v1/jobs/{uid}/retry", headers=key, json=body | {"from_stage": "stage0"}
        ).status_code
        == 409
    )
    run_job(engine, settings, uid, 1)  # Stale broker message must not execute retry attempt.
    assert client.get(f"/api/v1/jobs/{uid}").json()["status"] == "queued"
    run_job(engine, settings, uid, 2)
    with Session(engine) as db:
        stages = stages_for(db, uid)
        assert [s.completed_attempt for s in stages] == [1, 2]
        assert db.get(Job, uid).status == "succeeded"


def test_expired_token_and_old_identity_are_fenced(jobs):
    _, _, _, make, engine, settings = jobs
    uid = make()
    token = claim(engine, uid, 1, settings.job_lease_seconds)
    with Session(engine, expire_on_commit=False) as old:
        stale = old.get(Job, uid)
        with Session(engine) as other:
            row = other.get(Job, uid)
            row.lease_until = now() - timedelta(seconds=1)
            other.commit()
        with pytest.raises(LostLease):
            locked(old, uid, token)
        old.rollback()
        assert recover_expired(engine) == 1
        new = claim(engine, uid, 1, settings.job_lease_seconds)
        assert new != token and stale.id == uid
        with pytest.raises(LostLease):
            locked(old, uid, token)


def test_unknown_call_blocks_retry_even_after_cancel(jobs):
    client, headers, _, make, engine, settings = jobs
    uid = make(["fixture.unknown"])
    run_job(engine, settings, uid, 1)
    failed = client.get(f"/api/v1/jobs/{uid}").json()
    assert failed["error"]["code"] == "call_result_unknown" and not failed["can_retry"]
    assert set(failed["error"]) == {"code", "message", "request_id", "details"}
    assert (
        client.post(
            f"/api/v1/jobs/{uid}/cancel",
            headers=headers,
            json={"expected_revision": failed["revision"]},
        ).status_code
        == 200
    )
    response = client.post(
        f"/api/v1/jobs/{uid}/retry",
        headers=headers | {"Idempotency-Key": str(uuid4())},
        json={"expected_revision": failed["revision"], "from_stage": "stage0"},
    )
    assert response.status_code == 409


def test_intent_survives_worker_loss_and_known_result_reused(jobs):
    client, _, _, make, engine, settings = jobs
    uid = make()
    token = claim(engine, uid, 1, settings.job_lease_seconds)
    with Session(engine) as db:
        stage = stages_for(db, uid)[0]
        stage.status = "running"
        db.commit()
        sid = stage.id
    ctx = Context(engine, uid, token, sid, settings.job_lease_seconds)
    intent = ctx.begin_paid_call("synthetic")
    assert intent["execute"]
    with Session(engine) as db:
        row = db.get(Job, uid)
        row.lease_until = now() - timedelta(seconds=1)
        db.commit()
    recover_expired(engine)
    assert client.get(f"/api/v1/jobs/{uid}").json()["can_retry"] is False
    known = make()
    token = claim(engine, known, 1, settings.job_lease_seconds)
    with Session(engine) as db:
        sid = stages_for(db, known)[0].id
    ctx = Context(engine, known, token, sid, settings.job_lease_seconds)
    first = ctx.begin_paid_call("known")
    ctx.finish_paid_call(first["intent_id"], {"synthetic": True})
    cached = ctx.begin_paid_call("known")
    assert not cached["execute"] and cached["result"] == {"synthetic": True}


def test_outbox_failure_and_redelivery(jobs):
    _, _, _, make, engine, settings = jobs
    uid = make()

    def fail(event, settings):
        raise ConnectionError("synthetic broker failure")

    assert dispatch_once(engine, settings, fail)
    with Session(engine) as db:
        event = db.scalar(select(Outbox).where(Outbox.job_id == uid))
        assert event.status == "pending" and event.delivery_attempts == 1
        event.next_attempt_at = now()
        db.commit()
    sent = []
    dispatch_once(engine, settings, lambda event, _: sent.append((event.job_id, event.attempt)))
    assert sent == [(uid, 1)]


def test_cookie_csrf_workspace_and_production_handler_guard(jobs):
    client, headers, admin, make, engine, settings = jobs
    uid = make()
    assert client.get(f"/api/v1/jobs/{uuid4()}").status_code == 404
    from live_review.modules.identity.models import Workspace

    with Session(engine) as db:
        foreign = Workspace(name="Synthetic foreign workspace")
        db.add(foreign)
        db.flush()
        job = db.get(Job, uid)
        job.workspace_id = foreign.id
        db.commit()
        try:
            assert client.get(f"/api/v1/jobs/{uid}").status_code == 404
            assert (
                client.post(
                    f"/api/v1/jobs/{uid}/cancel",
                    headers=headers,
                    json={"expected_revision": 1},
                ).status_code
                == 404
            )
        finally:
            job.workspace_id = admin.workspace_id
            db.delete(foreign)
            db.commit()
    assert (
        client.post(f"/api/v1/jobs/{uid}/cancel", json={"expected_revision": 1}).status_code == 403
    )
    settings.job_test_handlers = False
    run_job(engine, settings, uid, 1)
    assert client.get(f"/api/v1/jobs/{uid}").json()["error"]["code"] == "handler_unavailable"
    client.cookies.clear()
    assert client.get(f"/api/v1/jobs/{uid}").status_code == 401


def test_skipped_stage_preserved_by_retry(jobs):
    client, headers, _, make, engine, settings = jobs
    uid = make(["fixture.skip", "fixture.fail_once"])
    run_job(engine, settings, uid, 1)
    result = client.get(f"/api/v1/jobs/{uid}").json()
    assert result["steps"][0] == {
        "stage": "stage0",
        "status": "skipped",
        "reason": "not_applicable",
    }
    assert (
        client.post(
            f"/api/v1/jobs/{uid}/retry",
            headers=headers | {"Idempotency-Key": str(uuid4())},
            json={"expected_revision": result["revision"], "from_stage": "stage1"},
        ).status_code
        == 202
    )
    run_job(engine, settings, uid, 2)
    with Session(engine) as db:
        stages = stages_for(db, uid)
        assert stages[0].status == "skipped" and stages[0].artifact is None
        assert [s.completed_attempt for s in stages] == [1, 2]
        assert db.get(Job, uid).status == "succeeded"


def test_cancel_confirms_uncooperative_child_stopped(jobs):
    import multiprocessing
    import time

    client, headers, _, make, engine, settings = jobs
    uid = make(["fixture.uncooperative"], {"delay_seconds": 30})
    previous = {p.pid for p in multiprocessing.active_children()}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_job, engine, settings, uid, 1)
        child = None
        for _ in range(100):
            candidates = [p for p in multiprocessing.active_children() if p.pid not in previous]
            if candidates:
                child = candidates[0]
                break
            time.sleep(0.05)
        assert child is not None
        result = client.get(f"/api/v1/jobs/{uid}").json()
        canceled = client.post(
            f"/api/v1/jobs/{uid}/cancel",
            headers=headers,
            json={"expected_revision": result["revision"]},
        )
        assert canceled.status_code == 202 and canceled.json()["status"] == "cancel_requested"
        future.result(timeout=8)
        assert not child.is_alive() and child.exitcode is not None
    result = client.get(f"/api/v1/jobs/{uid}").json()
    assert result["status"] == "canceled" and result["cancel_requested"]
    with Session(engine) as db:
        assert stages_for(db, uid)[0].artifact is None


def test_cancel_then_worker_loss_does_not_claim_confirmed_stop(jobs):
    client, headers, _, make, engine, settings = jobs
    uid = make()
    claim(engine, uid, 1, settings.job_lease_seconds)
    result = client.get(f"/api/v1/jobs/{uid}").json()
    client.post(
        f"/api/v1/jobs/{uid}/cancel",
        headers=headers,
        json={"expected_revision": result["revision"]},
    )
    with Session(engine) as db:
        job = db.get(Job, uid)
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    recover_expired(engine)
    result = client.get(f"/api/v1/jobs/{uid}").json()
    assert result["status"] == "failed" and not result["can_retry"]
    assert result["error"]["code"] == "execution_stop_unconfirmed"


def test_migration_metadata_matches_real_postgres(jobs):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from live_review.core.database import Base

    *_, engine, _ = jobs
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_unconfirmed_handler_stop_blocks_retry(jobs, monkeypatch):
    from live_review.workers.handler_process import StopUnconfirmed

    client, headers, _, make, engine, settings = jobs
    uid = make()

    def cannot_stop(*args):
        raise StopUnconfirmed

    monkeypatch.setattr("live_review.workers.job_runner.execute_handler", cannot_stop)
    run_job(engine, settings, uid, 1)
    result = client.get(f"/api/v1/jobs/{uid}").json()
    assert result["error"]["code"] == "execution_stop_unconfirmed"
    assert not result["can_retry"]
    assert (
        client.post(
            f"/api/v1/jobs/{uid}/retry",
            headers=headers | {"Idempotency-Key": str(uuid4())},
            json={"expected_revision": result["revision"], "from_stage": "stage0"},
        ).status_code
        == 409
    )


def test_process_boundary_raises_stop_unconfirmed(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from live_review.modules.jobs.execution import Canceled
    from live_review.workers.handler_process import StopUnconfirmed, execute_handler

    process = Mock(pid=123456, is_alive=Mock(return_value=True))
    factory = Mock()
    factory.Process.return_value = process
    factory.Pipe.return_value = (Mock(), Mock())
    monkeypatch.setattr(
        "live_review.workers.handler_process.multiprocessing.get_context", lambda _: factory
    )
    monkeypatch.setattr("live_review.workers.handler_process.os.killpg", lambda *_: None)
    context = Mock(job_id=uuid4(), token=uuid4(), stage_id=uuid4())
    context.heartbeat.side_effect = Canceled
    with pytest.raises(StopUnconfirmed):
        execute_handler(
            context, SimpleNamespace(job_test_handlers=False, job_lease_seconds=3), "synthetic.test"
        )
    assert process.join.call_count == 2
