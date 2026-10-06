"""No autostart or downloads: connect only to an explicitly provisioned local worker."""

import asyncio
import base64
from contextlib import suppress

from ..contracts import ASRError, ASREvent, ASRHealth, ASRResult
from .protocol import MAX_CHUNK, MAX_FRAME, fingerprint, read, safe_code, socket_path, write

STOP_TIMEOUT_SECONDS = 5


async def confirm_stopped(reader, writer, *, send_cancel=True):
    """Keep the channel open until server cleanup is acknowledged, or mark it unconfirmed."""

    async def exchange():
        async with asyncio.timeout(STOP_TIMEOUT_SECONDS):
            if send_cancel:
                with suppress(ConnectionError):
                    await write(writer, {"type": "cancel"})
            while True:
                message = await read(reader)
                if message == {"type": "stopped"}:
                    return

    cleanup = asyncio.create_task(exchange())
    try:
        while True:
            try:
                await asyncio.shield(cleanup)
                return
            except asyncio.CancelledError:
                # Repeated caller cancellation must not turn an unverified stop into success.
                if cleanup.done():
                    raise ASRError("worker_stop_unconfirmed", unknown=True) from None
    except Exception:
        raise ASRError("worker_stop_unconfirmed", unknown=True) from None


class LocalWorkerProvider:
    def __init__(self, socket_path, config):
        self.socket_path, self.config = socket_path, config
        self.fingerprint = fingerprint(config)

    async def _connect(self, op, request=None, path=None, request_id=None):
        if request and (request.allow_network or request.privacy != "local_only"):
            raise ASRError("worker_local_only_required")
        try:
            path_to_socket = socket_path(self.socket_path, existing=True)
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(path_to_socket), limit=MAX_FRAME), 5
            )
        except (OSError, TimeoutError):
            raise ASRError("worker_unavailable") from None
        payload = {"op": op, "fingerprint": self.fingerprint}
        if request:
            payload["request"] = request.model_dump(mode="json")
        if path is not None:
            payload["path"] = str(path)
        if request_id is not None:
            payload["request_id"] = request_id
        try:
            await write(writer, payload)
            return reader, writer
        except BaseException:
            try:
                if request:
                    await confirm_stopped(reader, writer)
            finally:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
            raise

    async def _response(self, reader):
        value = await read(reader)
        return value

    async def _single(self, op, request=None, path=None):
        reader, writer = None, None
        terminal, stopped = False, False
        try:
            timeout = (
                5
                if request is None
                else (request.max_duration_seconds + self.config.lock_timeout_seconds + 120)
            )
            async with asyncio.timeout(timeout):
                reader, writer = await self._connect(op, request, path)
                value = await self._response(reader)
                terminal = value.get("type") in {"result", "error"}
                if value == {"type": "stopped"}:
                    stopped = True
                    raise ASRError("worker_canceled")
                if value.get("type") == "error":
                    raise ASRError(safe_code(ASRError(value.get("code"))))
                if value.get("type") != ("health" if op == "health" else "result"):
                    raise ASRError("worker_response_invalid")
                model = ASRHealth if op == "health" else ASRResult
                result = model.model_validate(value["data"])
                if op == "health" and result.network_checked:
                    raise ASRError("worker_response_invalid")
                if op != "health" and result.source != "local":
                    raise ASRError("worker_response_invalid")
                return result
        except ASRError:
            raise
        except TimeoutError:
            raise ASRError("worker_timeout") from None
        except Exception:
            raise ASRError("worker_response_invalid") from None
        finally:
            if writer:
                try:
                    if request and not stopped:
                        await confirm_stopped(reader, writer, send_cancel=not terminal)
                finally:
                    writer.close()
                    with suppress(Exception):
                        await writer.wait_closed()

    async def cancel_and_wait(self, request_id):
        """External supervisor cancellation; also fences a not-yet-connected request ID."""
        writer = None
        try:
            async with asyncio.timeout(STOP_TIMEOUT_SECONDS + 1):
                reader, writer = await self._connect("cancel", request_id=request_id)
                response = await read(reader)
                if response != {"type": "cancel_status", "stopped": True}:
                    raise ASRError("worker_stop_unconfirmed", unknown=True)
        except BaseException:
            raise ASRError("worker_stop_unconfirmed", unknown=True) from None
        finally:
            if writer:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()

    async def health(self):
        return await self._single("health")

    async def transcribe_file(self, path, request):
        return await self._single("file", request, path)

    async def transcribe_stream(self, chunks, request):
        writer, sender, receiver = None, None, None
        stopped = False
        try:
            async with asyncio.timeout(
                request.max_duration_seconds + self.config.lock_timeout_seconds + 120
            ):
                reader, writer = await self._connect("stream", request)

                async def upload():
                    total = 0
                    async for chunk in chunks:
                        if not isinstance(chunk, bytes) or not chunk or len(chunk) > MAX_CHUNK:
                            raise ASRError("worker_pcm_invalid")
                        total += len(chunk)
                        if total > request.max_duration_seconds * 32000:
                            raise ASRError("worker_duration_exceeded")
                        await write(
                            writer, {"type": "pcm", "data": base64.b64encode(chunk).decode()}
                        )
                    await write(writer, {"type": "end"})

                sender = asyncio.create_task(upload())
                while True:
                    receiver = asyncio.create_task(self._response(reader))
                    watched = {receiver} if sender.done() else {sender, receiver}
                    done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
                    if sender in done or sender.done():
                        await sender
                    value = await receiver
                    receiver = None
                    if value == {"type": "stopped"}:
                        stopped = True
                        raise ASRError("worker_canceled")
                    if value.get("type") == "error":
                        await confirm_stopped(reader, writer, send_cancel=False)
                        stopped = True
                        raise ASRError(safe_code(ASRError(value.get("code"))))
                    if value.get("type") != "event":
                        raise ASRError("worker_response_invalid")
                    event = ASREvent.model_validate(value["data"])
                    if event.result and event.result.source != "local":
                        raise ASRError("worker_response_invalid")
                    if event.type == "error":
                        event = event.model_copy(update={"code": safe_code(ASRError(event.code))})
                    if event.type in {"completed", "error"}:
                        await sender
                        await confirm_stopped(reader, writer, send_cancel=False)
                        stopped = True
                        yield event
                        return
                    yield event
        except ASRError:
            raise
        except TimeoutError:
            raise ASRError("worker_timeout") from None
        except Exception:
            raise ASRError("worker_response_invalid") from None
        finally:
            tasks = [task for task in (sender, receiver) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if writer:
                try:
                    if not stopped:
                        await confirm_stopped(reader, writer)
                finally:
                    writer.close()
                    with suppress(Exception):
                        await writer.wait_closed()
