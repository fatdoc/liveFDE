"""Real isolated PostgreSQL and authenticated sockets; synthetic provider only."""

import time
from types import SimpleNamespace
from uuid import UUID

import pytest
from jobs_fixture import jobs as jobs
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from live_review.integrations.asr_gateway.contracts import ASRError, ASREvent, ASRResult, ASRSegment
from live_review.main import app
from live_review.modules.asr import stream
from live_review.modules.asr.schemas import SettingsOutput
from live_review.modules.asr.service import authorization
from live_review.modules.jobs.models import CallIntent, Job, JobStage, Outbox

PATH = "/api/v1/asr/stream"
ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def setup(jobs, monkeypatch):
    client, headers, admin, _, engine, settings = jobs
    if not any(getattr(route, "path", None) == PATH for route in app.routes):
        app.include_router(stream.router)
    state = {"calls": 0, "mode": "success", "cloud": False, "fallback": False}

    def prepare(db, actor, config, data):
        prefs = SettingsOutput(
            revision=0,
            provider="tencent" if state["cloud"] else "local",
            privacy="cloud_allowed" if state["cloud"] else "local_only",
            allow_cloud_fallback=state["fallback"],
        )
        grant = authorization(prefs, data)
        registry = SimpleNamespace(
            loaded=SimpleNamespace(
                public=SimpleNamespace(media=SimpleNamespace(max_duration_seconds=1))
            )
        )
        return registry, {"preferences": prefs.model_dump(), "authorization": grant}

    class Gateway:
        def __init__(self, registry, prefs, grant, recorder):
            self.prefs, self.recorder = prefs, recorder

        async def transcribe_stream(self, chunks, request):
            if self.prefs.provider == "tencent":
                async for event in self.recorder.stream(self, chunks, request):
                    yield event
            else:
                async for event in self.events(chunks, request):
                    yield event

        async def events(self, chunks, request):
            state["calls"] += 1
            data = b""
            async for chunk in chunks:
                data += chunk
                if state["mode"] == "unknown":
                    raise ASRError("synthetic_cloud_unknown", unknown=True)
            segment = ASRSegment(
                id="0", text="合成", start_ms=0, end_ms=200, timestamp_source="provider"
            )
            yield ASREvent(type="final", segment=segment)
            result = ASRResult(
                provider="synthetic",
                model="mock",
                segments=(segment,),
                complete=state["mode"] != "incomplete",
                duration_ms=200,
                elapsed_ms=1,
                synthetic=True,
                source="cloud" if self.prefs.provider == "tencent" else "local",
            )
            yield ASREvent(type="completed", result=result)

    # CloudRecorder receives a provider exposing the same name, without recursion.
    original = Gateway.transcribe_stream

    async def route(self, chunks, request):
        if self.prefs.provider == "tencent":
            provider = SimpleNamespace(transcribe_stream=self.events)
            async for event in self.recorder.stream(provider, chunks, request):
                yield event
        else:
            async for event in original(self, chunks, request):
                yield event

    Gateway.transcribe_stream = route
    monkeypatch.setattr(stream, "prepare", prepare)
    monkeypatch.setattr(stream, "ASRGateway", Gateway)
    return client, headers, admin, engine, state


def start(headers, **extra):
    return {"type": "start", "csrf_token": headers["X-CSRF-Token"], "expected_revision": 0, **extra}


def wait_terminal(engine, job_id):
    for _ in range(100):
        with Session(engine) as db:
            row = db.get(Job, UUID(job_id))
            if row.status in {"succeeded", "failed", "canceled"}:
                return row.status, row.error
        time.sleep(0.01)
    raise AssertionError("stream did not finalize")


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://untrusted.invalid"}, ORIGIN | {"Sec-Fetch-Site": "cross-site"}],
)
def test_origin_required_before_accept(setup, headers):
    client, _, _, _, state = setup
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(PATH, headers=headers):
            pass
    assert state["calls"] == 0


def test_cookie_required(setup):
    client, _, _, _, state = setup
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(PATH, headers=ORIGIN):
            pass
    assert state["calls"] == 0


@pytest.mark.parametrize(
    "change,code",
    [
        ({"csrf_token": "invalid"}, "csrf_rejected"),
        ({"expected_revision": 2}, "revision_conflict"),
        ({"allow_network": True}, "local_only_forbids_cloud"),
    ],
)
def test_start_rejection_does_not_create_job(setup, change, code):
    client, headers, admin, engine, state = setup
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.send_json(start(headers) | change)
        assert ws.receive_json()["code"] == code
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Job).where(Job.workspace_id == admin.workspace_id)
            )
            == 0
        )
    assert state["calls"] == 0


@pytest.mark.parametrize("cloud", [False, True])
def test_success_persisted_without_outbox_and_no_retry(setup, cloud):
    client, headers, admin, engine, state = setup
    state["cloud"] = cloud
    grant = {"allow_network": True, "max_requests": 1, "max_cost_usd": 0.1} if cloud else {}
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.send_json(start(headers, **grant))
        begun = ws.receive_json()
        assert begun["type"] == "started"
        ws.send_bytes(b"\0\0" * 3200)
        ws.send_json({"type": "end"})
        assert ws.receive_json()["type"] == "final"
        assert ws.receive_json()["type"] == "completed"
    identifier = UUID(begun["job_id"])
    with Session(engine) as db:
        job = db.get(Job, identifier)
        assert job.workspace_id == admin.workspace_id and job.status == "succeeded"
        assert job.lease_token is None and job.input_data["kind"] == "asr_stream_v1"
        assert db.scalar(select(Outbox).where(Outbox.job_id == identifier)) is None
        stage = db.scalar(select(JobStage).where(JobStage.job_id == identifier))
        assert stage.artifact and stage.status == "succeeded"
        intents = db.scalars(select(CallIntent).where(CallIntent.job_id == identifier)).all()
        assert len(intents) == int(cloud)
        assert all(intent.state == "known" for intent in intents)
    assert state["calls"] == 1
    assert not client.get(f"/api/v1/jobs/{identifier}").json()["can_retry"]


@pytest.mark.parametrize("mode", ["unknown", "incomplete"])
def test_failed_cloud_preserves_unknown_or_partial_artifact(setup, mode):
    client, headers, _, engine, state = setup
    state.update(cloud=True, mode=mode)
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.send_json(start(headers, allow_network=True, max_requests=1, max_cost_usd=0.1))
        identifier = UUID(ws.receive_json()["job_id"])
        ws.send_bytes(b"\0\0" * 3200)
        if mode == "incomplete":
            ws.send_json({"type": "end"})
            assert ws.receive_json()["type"] == "final"
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == (
            "call_result_unknown" if mode == "unknown" else "transcript_incomplete"
        )
    with Session(engine) as db:
        job = db.get(Job, identifier)
        intent = db.scalar(select(CallIntent).where(CallIntent.job_id == identifier))
        stage = db.scalar(select(JobStage).where(JobStage.job_id == identifier))
        assert job.status == "failed" and job.lease_token is None
        assert intent.state == ("unknown" if mode == "unknown" else "known")
        assert bool(stage.artifact) == (mode == "incomplete")
    view = client.get(f"/api/v1/jobs/{identifier}").json()
    assert not view["can_retry"]
    response = client.post(
        f"/api/v1/jobs/{identifier}/retry",
        headers=headers | {"Idempotency-Key": "synthetic-retry"},
        json={"expected_revision": view["revision"], "from_stage": "asr"},
    )
    assert response.status_code == 409 and state["calls"] == 1


@pytest.mark.parametrize("action", ["cancel", "disconnect", "oversize", "idle"])
def test_interruption_and_limits_release_lease(setup, monkeypatch, action):
    client, headers, _, engine, _ = setup
    monkeypatch.setattr(stream, "INPUT_IDLE_SECONDS", 0.01)
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.send_json(start(headers))
        identifier = ws.receive_json()["job_id"]
        if action == "cancel":
            ws.send_json({"type": "cancel"})
        elif action == "oversize":
            ws.send_bytes(b"\0" * 32002)
        elif action == "disconnect":
            ws.close()
        if action != "disconnect":
            assert ws.receive_json()["type"] == "error"
    status, _ = wait_terminal(engine, identifier)
    assert status in {"failed", "canceled"}
    with Session(engine) as db:
        assert db.get(Job, UUID(identifier)).lease_token is None


@pytest.mark.parametrize("fallback", [False, True])
def test_cloud_grant_and_stream_fallback_rejected(setup, fallback):
    client, headers, _, _, state = setup
    state.update(cloud=True, fallback=fallback)
    grant = {"allow_network": True, "max_requests": 1, "max_cost_usd": 0.1} if fallback else {}
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.send_json(start(headers, **grant))
        assert ws.receive_json()["code"] == (
            "stream_fallback_not_supported" if fallback else "cloud_authorization_required"
        )
    assert state["calls"] == 0


def test_cloud_cancel_keeps_unknown_intent(setup):
    client, headers, _, engine, state = setup
    state["cloud"] = True
    with client.websocket_connect(PATH, headers=ORIGIN) as ws:
        ws.send_json(start(headers, allow_network=True, max_requests=1, max_cost_usd=0.1))
        identifier = UUID(ws.receive_json()["job_id"])
        # Wait until the durable pre-call intent exists before canceling.
        for _ in range(100):
            with Session(engine) as db:
                if db.scalar(select(CallIntent).where(CallIntent.job_id == identifier)):
                    break
            time.sleep(0.01)
        else:
            raise AssertionError("missing intent")
        ws.send_json({"type": "cancel"})
        assert ws.receive_json()["code"] == "call_result_unknown"
    with Session(engine) as db:
        assert db.get(Job, identifier).status == "failed"
        assert (
            db.scalar(select(CallIntent).where(CallIntent.job_id == identifier)).state == "unknown"
        )
