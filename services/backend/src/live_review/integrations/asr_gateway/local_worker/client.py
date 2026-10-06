"""No autostart or downloads: connect only to an explicitly provisioned local worker."""

import asyncio
import base64
from contextlib import suppress

from ..contracts import ASRError, ASREvent, ASRHealth, ASRResult
from .protocol import MAX_CHUNK, MAX_FRAME, fingerprint, read, safe_code, socket_path, write


class LocalWorkerProvider:
    def __init__(self, socket_path, config):
        self.socket_path, self.config = socket_path, config
        self.fingerprint = fingerprint(config)

    async def _connect(self, op, request=None, path=None):
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
        try:
            await write(writer, payload)
            return reader, writer
        except BaseException:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            raise

    async def _response(self, reader):
        value = await read(reader)
        if value.get("type") == "error":
            raise ASRError(safe_code(ASRError(value.get("code"))))
        return value

    async def _single(self, op, request=None, path=None):
        writer = None
        try:
            timeout = (
                5
                if request is None
                else (request.max_duration_seconds + self.config.lock_timeout_seconds + 120)
            )
            async with asyncio.timeout(timeout):
                reader, writer = await self._connect(op, request, path)
                value = await self._response(reader)
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
                writer.close()  # EOF is a cancellation signal; server waits for inference cleanup.
                with suppress(Exception):
                    await writer.wait_closed()

    async def health(self):
        return await self._single("health")

    async def transcribe_file(self, path, request):
        return await self._single("file", request, path)

    async def transcribe_stream(self, chunks, request):
        writer, sender, receiver = None, None, None
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
                    if value.get("type") != "event":
                        raise ASRError("worker_response_invalid")
                    event = ASREvent.model_validate(value["data"])
                    if event.result and event.result.source != "local":
                        raise ASRError("worker_response_invalid")
                    if event.type == "error":
                        event = event.model_copy(update={"code": safe_code(ASRError(event.code))})
                    if event.type in {"completed", "error"}:
                        await sender
                        writer.close()
                        with suppress(Exception):
                            await writer.wait_closed()
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
            if writer:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
            await asyncio.gather(*tasks, return_exceptions=True)
