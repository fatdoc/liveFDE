"""V2 sentence stream only; concurrent receive and sample-count 1:1 PCM pacing."""

import asyncio
import json
import secrets
import time
from uuid import uuid4

from live_review.integrations.asr_gateway.contracts import ASRError, ASREvent
from live_review.integrations.asr_gateway.tencent.config import authorize
from live_review.integrations.asr_gateway.tencent.results import result, segment
from live_review.integrations.asr_gateway.tencent.signing import realtime_url


def connect_websocket(url, timeout):
    # Optional dependency is imported only after explicit authorization/capability checks.
    import websocket

    websocket.enableTrace(False)
    return websocket.create_connection(
        url, timeout=timeout, enable_multithread=True, http_no_proxy=["*"], redirect_limit=0
    )


def decode_message(raw, voice_id):
    if not isinstance(raw, str) or len(raw.encode()) > 1024 * 1024:
        raise ASRError("tencent_result_unknown", unknown=True)
    try:
        message = json.loads(raw)
        if message.get("voice_id") != voice_id:
            raise ASRError("tencent_result_unknown", unknown=True)
        if message.get("code") != 0:
            raise ASRError("tencent_stream_rejected")
        return message
    except (ValueError, TypeError, AttributeError):
        raise ASRError("tencent_result_unknown", unknown=True) from None


class RealtimeRecognizer:
    def __init__(self, config, connector=None):
        self.config, self.connector = config, connector or connect_websocket

    async def stream(self, chunks, request):
        authorize(self.config, request, stream=True)
        config, started, voice_id = self.config, time.monotonic(), str(uuid4())
        now = int(time.time())
        params = {
            "secretid": config.secret_id.get_secret_value(),
            "timestamp": now,
            "expired": now + 600,
            "nonce": secrets.randbelow(9_999_999_999) + 1,
            "engine_model_type": config.engine_stream,
            "voice_id": voice_id,
            "voice_format": 1,
            "needvad": 1,
            "result_mod": 1,
            "speaker_diarization": int(request.speaker),
            "filter_dirty": 0,
            "filter_modal": 0,
            "convert_num_mode": 0,
        }
        url = realtime_url(config.app_id, config.secret_key.get_secret_value(), params)
        ws, sender, receiver = None, None, None
        sent_bytes, ended = [0], asyncio.Event()
        observations = {}
        deadline = started + config.timeout_seconds
        try:
            # Connection creation is bounded by socket timeout; preserve its handle for cleanup.
            connecting = asyncio.create_task(
                asyncio.to_thread(
                    self.connector, url, min(config.io_timeout_seconds, config.timeout_seconds)
                )
            )
            try:
                ws = await asyncio.shield(connecting)
            except asyncio.CancelledError:
                # Native connection cannot be cancelled: retain it and close its eventual socket.
                ws = await connecting
                raise
            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                decode_message(await asyncio.to_thread(ws.recv), voice_id)

            async def send_audio():
                stream_start, pending = time.monotonic(), bytearray()
                pace_at = stream_start

                async def send(part):
                    nonlocal pace_at
                    wait = pace_at - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    if time.monotonic() - pace_at > 5:
                        raise ASRError("tencent_stream_input_stalled", unknown=True)
                    if sent_bytes[0] + len(part) > request.max_duration_seconds * 32000:
                        raise ASRError("audio_duration_limit", unknown=True)
                    await asyncio.to_thread(ws.send_binary, bytes(part))
                    sent_bytes[0] += len(part)
                    pace_at = time.monotonic() + len(part) / 32000

                iterator = aiter(chunks)
                while True:
                    try:
                        async with asyncio.timeout(min(5, max(0, deadline - time.monotonic()))):
                            chunk = await anext(iterator)
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        raise ASRError("tencent_stream_input_stalled", unknown=True) from None
                    if not isinstance(chunk, bytes) or len(chunk) > 1024 * 1024:
                        raise ASRError("invalid_pcm_chunk", unknown=sent_bytes[0] > 0)
                    pending.extend(chunk)
                    while len(pending) >= 6400:
                        await send(pending[:6400])
                        del pending[:6400]
                if len(pending) % 2:
                    raise ASRError("invalid_pcm_sample", unknown=sent_bytes[0] > 0)
                if pending:
                    await send(pending)
                if not sent_bytes[0]:
                    raise ASRError("empty_audio")
                wait = pace_at - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                ended.set()
                await asyncio.to_thread(ws.send, '{"type":"end"}')

            sender = asyncio.create_task(send_audio())
            while True:
                if sender.done():
                    await sender
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ASRError("tencent_result_unknown", unknown=True)
                receiver = asyncio.create_task(asyncio.to_thread(ws.recv))
                watched = {receiver} if sender.done() else {receiver, sender}
                done, _ = await asyncio.wait(
                    watched, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    raise ASRError("tencent_result_unknown", unknown=True)
                if sender in done:
                    await sender  # Propagate upload/input failure even when receive is blocked.
                async with asyncio.timeout(max(0, deadline - time.monotonic())):
                    message = decode_message(await receiver, voice_id)
                receiver = None
                sentences = message.get("sentences", {})
                if not isinstance(sentences, dict) or "result" in message:
                    raise ASRError("tencent_result_unknown", unknown=True)
                # Protocol table shows a direct sentence; official Python V2 SDK uses a list.
                rows = (
                    [sentences] if "sentence" in sentences else sentences.get("sentence_list", [])
                )
                if not isinstance(rows, list) or len(rows) > 2000:
                    raise ASRError("tencent_result_unknown", unknown=True)
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get("sentence"), str):
                        raise ASRError("tencent_result_unknown", unknown=True)
                    identifier = row.get("sentence_id")
                    if type(identifier) is not int or identifier < 0:
                        raise ASRError("tencent_result_unknown", unknown=True)
                    item = segment(
                        identifier,
                        row["sentence"],
                        row.get("start_time"),
                        row.get("end_time"),
                        row.get("speaker_id") if request.speaker else None,
                        final=row.get("sentence_type") == 1,
                        duration_ms=request.max_duration_seconds * 1000,
                    )
                    observations[identifier] = item
                    if len(observations) > 10000:
                        raise ASRError("tencent_result_unknown", unknown=True)
                    yield ASREvent(type="final" if item.final else "partial", segment=item)
                if message.get("final") == 1:
                    if not ended.is_set():
                        raise ASRError("tencent_early_final", unknown=True)
                    await sender
                    duration_ms = (sent_bytes[0] * 1000 + 31999) // 32000
                    # Validate against actual sent audio, not only the configured upper bound.
                    values = [
                        item
                        if item.end_ms is None or item.end_ms <= duration_ms
                        else item.model_copy(
                            update={
                                "start_ms": None,
                                "end_ms": None,
                                "timestamp_source": "unavailable",
                            }
                        )
                        for _, item in sorted(observations.items())
                    ]
                    completed = result(
                        config.engine_stream,
                        values,
                        request,
                        duration_ms,
                        round((time.monotonic() - started) * 1000),
                    )
                    yield ASREvent(type="completed", result=completed)
                    break
        except ASRError as error:
            if sent_bytes[0] and not error.unknown:
                raise ASRError(error.code, unknown=True) from None
            raise
        except (Exception, asyncio.CancelledError):
            raise ASRError("tencent_result_unknown", unknown=True) from None
        finally:
            if ws is not None:
                try:
                    await asyncio.to_thread(ws.close)
                except Exception:
                    pass
            tasks = [task for task in (sender, receiver) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
