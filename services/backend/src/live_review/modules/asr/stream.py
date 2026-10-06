"""Authenticated, non-replayable PCM sessions owned by the connected WebSocket."""

import asyncio
import json
import re
import secrets
import time
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from live_review.core.auth import current_admin, require_origin
from live_review.core.errors import ApiError
from live_review.core.provider_config import ProviderConfigError
from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.service import ASRGateway
from live_review.modules.asr.schemas import Authorization, SettingsOutput
from live_review.modules.asr.service import prepare
from live_review.modules.jobs.execution import Canceled, Context, LostLease, claim, locked
from live_review.modules.jobs.models import CallIntent, JobStage, Outbox
from live_review.modules.jobs.service import create_job, safe_error, unknown_calls
from live_review.workers.asr_jobs import request_for
from live_review.workers.asr_recording import CloudRecorder
from live_review.workers.media_artifacts import write_json

router = APIRouter(prefix="/api/v1/asr", tags=["asr"])
START_TIMEOUT = 10
INPUT_IDLE_SECONDS = 10
MAX_CHUNK_BYTES = 64_000
MAX_STREAM_SECONDS = 300


def json_message(message):
    text = message.get("text")
    if not isinstance(text, str) or len(text.encode()) > 4096:
        raise ASRError("invalid_stream_control")
    try:
        data = json.loads(text)
    except ValueError:
        raise ASRError("invalid_stream_control") from None
    if not isinstance(data, dict):
        raise ASRError("invalid_stream_control")
    return data


def start_job(db, admin, settings, data):
    registry, payload = prepare(db, admin, settings, data)
    if payload["preferences"]["allow_cloud_fallback"]:
        raise ASRError("stream_fallback_not_supported")
    payload["kind"] = "asr_stream_v1"
    job = create_job(
        db, admin.workspace_id, admin.id, [{"name": "asr", "handler": "asr.stream"}], payload
    )
    # This ephemeral source belongs to this socket, not to the asynchronous dispatcher.
    db.execute(delete(Outbox).where(Outbox.job_id == job.id))
    stage = db.scalar(select(JobStage).where(JobStage.job_id == job.id))
    job_id, stage_id, workspace_id = job.id, stage.id, job.workspace_id
    db.commit()
    return registry, payload, job_id, stage_id, workspace_id


def finish(context, root, directory, result=None, code=None, canceled=False):
    reference = write_json(root, directory, result.model_dump(mode="json")) if result else None
    with Session(context.engine) as db:
        job = locked(db, context.job_id, context.token)
        stage = db.get(JobStage, context.stage_id)
        uncertain = unknown_calls(db, job.id) or code == "worker_stop_unconfirmed"
        if uncertain:
            code = (
                "worker_stop_unconfirmed"
                if code == "worker_stop_unconfirmed"
                else "call_result_unknown"
            )
            for intent in db.scalars(
                select(CallIntent).where(CallIntent.job_id == job.id, CallIntent.state == "intent")
            ):
                intent.state = "unknown"
        if result and not result.complete:
            code = code or "transcript_incomplete"
        if job.cancel_requested:
            canceled = True
        success = result is not None and result.complete and not code and not canceled
        status = "succeeded" if success else "canceled" if canceled and not uncertain else "failed"
        if success:
            code = None
        else:
            code = code or ("stream_canceled" if canceled else "stream_failed")
        job.status = stage.status = status
        job.error = safe_error(code, "实时识别未完成") if code else None
        stage.reason, stage.artifact = code, reference
        stage.completed_attempt = job.attempt if success else None
        job.lease_token = job.lease_until = None
        job.revision += 1
        db.commit()
        return status, code


async def run_stream(ws, context, gateway, request, max_seconds):
    queue = asyncio.Queue(maxsize=32)
    state = {"bytes": 0, "ended": False, "audio_at": time.monotonic()}
    send_lock = asyncio.Lock()

    async def send(data):
        async with send_lock:
            await ws.send_json(data)

    async def receive():
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            chunk = message.get("bytes")
            if chunk is not None:
                if state["ended"] or not chunk or len(chunk) % 2 or len(chunk) > MAX_CHUNK_BYTES:
                    raise ASRError("invalid_pcm_chunk")
                state["bytes"] += len(chunk)
                if state["bytes"] > max_seconds * 32000:
                    raise ASRError("audio_duration_limit")
                state["audio_at"] = time.monotonic()
                try:
                    queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    raise ASRError("stream_backpressure_limit") from None
                continue
            data = json_message(message)
            if data == {"type": "cancel"}:
                raise Canceled
            if data == {"type": "ping"}:
                await send({"type": "pong"})
            elif data == {"type": "end"} and not state["ended"] and state["bytes"]:
                state["ended"] = True
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    raise ASRError("stream_backpressure_limit") from None
            else:
                raise ASRError("invalid_stream_control")

    async def chunks():
        while (chunk := await queue.get()) is not None:
            yield chunk

    async def heartbeat():
        while True:
            await asyncio.to_thread(context.heartbeat)
            if not state["ended"] and time.monotonic() - state["audio_at"] > INPUT_IDLE_SECONDS:
                raise ASRError("stream_input_idle")
            await asyncio.sleep(min(1, context.lease_seconds / 3))

    async def consume():
        iterator = gateway.transcribe_stream(chunks(), request)
        try:
            async for event in iterator:
                if event.type == "error":
                    raise ASRError(event.code or "stream_provider_error", unknown=True)
                if event.type == "completed":
                    if not state["ended"] or event.result is None:
                        raise ASRError("stream_early_completion", unknown=True)
                    return event.result
                await send(event.model_dump(mode="json"))
            raise ASRError("stream_result_unknown", unknown=True)
        finally:
            await iterator.aclose()

    receiver, keeper, consumer = [asyncio.create_task(fn()) for fn in (receive, heartbeat, consume)]
    tasks = {receiver, keeper, consumer}
    try:
        async with asyncio.timeout(max_seconds + 30):
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            # A concurrent disconnect/cancel takes precedence over a completed transcript.
            for task in (receiver, keeper):
                if task in done:
                    await task
            return await consumer
    finally:
        for task in tasks:
            task.cancel()
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        if any(
            isinstance(error, ASRError) and error.code == "worker_stop_unconfirmed"
            for error in outcomes
        ):
            raise ASRError("worker_stop_unconfirmed", unknown=True)


@router.websocket("/stream")
async def stream(ws: WebSocket):
    settings, engine = ws.app.state.settings, ws.app.state.engine
    # Strict Origin and cookie identity checks occur before accepting/upgrading.
    try:
        require_origin(ws)
        with Session(engine, expire_on_commit=False) as db:
            admin = current_admin(ws, db)
            csrf = ws.state.auth_session.csrf_token
    except ApiError:
        await ws.close(code=1008)
        return
    await ws.accept()
    context, result, directory = None, None, None
    code, canceled = None, False
    try:
        async with asyncio.timeout(START_TIMEOUT):
            message = await ws.receive()
        data = json_message(message)
        supplied = data.pop("csrf_token", "")
        if (
            data.pop("type", None) != "start"
            or not isinstance(supplied, str)
            or not supplied.isascii()
            or not secrets.compare_digest(supplied, csrf)
        ):
            raise ASRError("csrf_rejected")
        grant = Authorization.model_validate(data)
        with Session(engine, expire_on_commit=False) as db:
            # Revalidate identity immediately before creating the durable workspace job.
            admin = current_admin(ws, db)
            registry, payload, job_id, stage_id, workspace_id = start_job(
                db, admin, settings, grant
            )
        token = claim(engine, job_id, 1, settings.job_lease_seconds)
        if token is None:
            raise ASRError("stream_claim_failed")
        context = Context(engine, job_id, token, stage_id, settings.job_lease_seconds)
        with Session(engine) as db:
            job = locked(db, job_id, token)
            job.current_stage = "asr"
            db.get(JobStage, stage_id).status = "running"
            db.commit()
        directory = f"jobs/{workspace_id}/{job_id}/{token}"
        preferences = SettingsOutput.model_validate(payload["preferences"])
        gateway = ASRGateway(
            registry,
            preferences,
            payload["authorization"],
            CloudRecorder(context, settings.storage_root, directory + "/calls"),
        )
        duration = min(MAX_STREAM_SECONDS, registry.loaded.public.media.max_duration_seconds)
        request = request_for(payload, f"{job_id}:1", duration)
        await ws.send_json(
            {"type": "started", "job_id": str(job_id), "max_duration_seconds": duration}
        )
        result = await run_stream(ws, context, gateway, request, duration)
    except (ASRError, ApiError, ProviderConfigError) as error:
        code = error.code if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", error.code) else "stream_failed"
    except (WebSocketDisconnect, Canceled, asyncio.CancelledError):
        code, canceled = "stream_canceled", True
    except TimeoutError:
        code = "stream_timeout"
    except ValidationError:
        code = "validation_error"
    except Exception:
        code = "stream_failed"
    finally:
        if context is not None:
            try:
                status, code = finish(
                    context, settings.storage_root, directory, result, code, canceled
                )
            except LostLease:
                status, code = "failed", "stream_lease_lost"
            except Exception:
                status, code = "failed", "stream_finalize_failed"
            with suppress(Exception):
                if status == "succeeded":
                    await ws.send_json(
                        {"type": "completed", "result": result.model_dump(mode="json")}
                    )
                else:
                    await ws.send_json(
                        {"type": "error", "code": code, "job_id": str(context.job_id)}
                    )
        elif code:
            with suppress(Exception):
                await ws.send_json({"type": "error", "code": code})
        with suppress(Exception):
            await ws.close(code=1000 if result and not code else 1008)
