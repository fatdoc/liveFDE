"""Real PG intent persistence; providers are explicit synthetic test doubles."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from jobs_fixture import jobs as jobs
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.integrations.asr_gateway.contracts import ASRError, ASRRequest, ASRResult
from live_review.modules.jobs.execution import Context, claim, recover_expired
from live_review.modules.jobs.models import CallIntent, Job, Outbox
from live_review.modules.jobs.service import now, stages_for, view
from live_review.workers.asr_recording import CloudRecorder


@pytest.mark.parametrize("outcome", ["known", "known_error", "unknown"])
def test_cloud_intent_committed_before_call_and_never_replayed(jobs, tmp_path, outcome):
    _, _, _, make, engine, _ = jobs
    uid = make(data={"kind": "asr_gateway_v1"})
    token = claim(engine, uid, 1, 30)
    with Session(engine) as db:
        stage_id = stages_for(db, uid)[0].id
    context = Context(engine, uid, token, stage_id, 30)
    calls = []
    result = ASRResult(
        provider="synthetic",
        model="fixture",
        segments=(),
        complete=True,
        duration_ms=1,
        elapsed_ms=1,
        synthetic=True,
        source="cloud",
    )

    async def transcribe_file(path, request):
        with Session(engine) as db:
            intent = db.scalar(select(CallIntent).where(CallIntent.job_id == uid))
            assert intent is not None and intent.state == "intent"
        calls.append(request.request_id)
        if outcome != "known":
            raise ASRError("synthetic_failure", unknown=outcome == "unknown")
        return result

    recorder = CloudRecorder(context, tmp_path, "calls")
    provider = SimpleNamespace(transcribe_file=transcribe_file)
    request = ASRRequest(request_id=str(uid), allow_network=True, privacy="cloud_allowed")
    for _ in range(2):
        if outcome == "known":
            assert asyncio.run(recorder.file(provider, tmp_path / "unused", request)) == result
        else:
            with pytest.raises(ASRError) as caught:
                asyncio.run(recorder.file(provider, tmp_path / "unused", request))
            assert caught.value.unknown == (outcome == "unknown")
    assert calls == [str(uid)]
    with Session(engine) as db:
        state = db.scalar(select(CallIntent.state).where(CallIntent.job_id == uid))
        assert state == ("intent" if outcome == "unknown" else "known")


def test_expired_shared_worker_file_requires_stop_verification(jobs):
    _, _, _, make, engine, _ = jobs
    uid = make(data={"kind": "asr_gateway_v1"})
    claim(engine, uid, 1, 30)
    with Session(engine) as db:
        db.get(Job, uid).lease_until = now() - timedelta(seconds=1)
        stages_for(db, uid)[0].status = "running"
        count = len(db.scalars(select(Outbox).where(Outbox.job_id == uid)).all())
        db.commit()
    recover_expired(engine)
    with Session(engine) as db:
        job = db.get(Job, uid)
        assert job.status == "failed" and job.error["code"] == "execution_stop_unconfirmed"
        assert not view(db, job)["can_retry"]
        assert len(db.scalars(select(Outbox).where(Outbox.job_id == uid)).all()) == count


@pytest.mark.parametrize("confirmed", [True, False])
def test_handler_failure_checks_external_stop_before_terminal(jobs, monkeypatch, confirmed):
    from live_review.workers import asr_stop
    from live_review.workers.job_runner import run_job

    client, _, _, make, engine, settings = jobs
    calls = []

    def confirm():
        calls.append("confirmation")
        if not confirmed:
            raise ASRError("worker_stop_unconfirmed", unknown=True)

    monkeypatch.setattr(asr_stop, "stop_guard", lambda *args: confirm)
    uid = make(["fixture.fail_once"])
    run_job(engine, settings, uid, 1)
    state = client.get(f"/api/v1/jobs/{uid}").json()
    assert state["status"] == "failed" and calls == ["confirmation"]
    assert state["error"]["code"] == ("stage_failed" if confirmed else "execution_stop_unconfirmed")
    assert state["can_retry"] is confirmed
