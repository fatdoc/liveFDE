"""One explicit local provider instance, serial inference, bounded Unix RPC connections."""

import asyncio
import base64
import os
import re
import socket
import wave
from contextlib import aclosing, suppress
from pathlib import Path

from ..contracts import ASRError, ASRRequest
from .protocol import MAX_CHUNK, MAX_FRAME, fingerprint, read, safe_code, socket_path, write


class LocalWorkerServer:
    def __init__(self, path, config, storage_root, provider, unload=None):
        self.path, self.config = Path(path), config
        self.storage_root = Path(storage_root)
        self.provider, self.unload = provider, unload
        self.fingerprint = fingerprint(config)
        self.server, self.identity = None, None
        self.connections = set()
        self.inference = asyncio.Lock()
        # Never evict tombstones: a late RPC must not revive a canceled request.
        self.requests = {}

    async def cancel_request(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,128}", request_id
        ):
            raise ASRError("worker_request_id_invalid")
        entry = self.requests.get(request_id)
        if entry is None:
            if len(self.requests) >= 4096:
                raise ASRError("worker_stop_unconfirmed", unknown=True)
            stopped = asyncio.Event()
            stopped.set()
            self.requests[request_id] = {"stopped": stopped, "task": None, "canceled": True}
            return
        if not entry["canceled"]:
            entry["canceled"] = True
            if not entry["stopped"].is_set():
                entry["task"].cancel()
        try:
            await asyncio.wait_for(entry["stopped"].wait(), 5)
        except TimeoutError:
            raise ASRError("worker_stop_unconfirmed", unknown=True) from None

    async def start(self):
        path = socket_path(self.path, existing=False)
        if (
            not self.storage_root.is_absolute()
            or self.storage_root.resolve() != self.storage_root
            or not self.storage_root.is_dir()
        ):
            raise ASRError("worker_path_rejected")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(
                str(path)
            )  # Never let start_unix_server unlink an existing foreign socket.
            os.chmod(path, 0o600)
            info = path.lstat()
            self.identity = (info.st_dev, info.st_ino)
            listener.setblocking(False)
            self.server = await asyncio.start_unix_server(
                self.handle, sock=listener, limit=MAX_FRAME
            )
        except BaseException:
            listener.close()
            self._unlink_owned()
            raise
        return self

    def _unlink_owned(self):
        with suppress(FileNotFoundError):
            info = self.path.lstat()
            if (info.st_dev, info.st_ino) == self.identity:
                self.path.unlink()

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.unload:
            await self.unload()
        self._unlink_owned()

    def audio_path(self, raw, request):
        if not isinstance(raw, str):
            raise ASRError("worker_path_rejected")
        path = Path(raw)
        if (
            not path.is_absolute()
            or path.resolve() != path
            or not path.is_file()
            or not path.is_relative_to(self.storage_root)
        ):
            raise ASRError("worker_path_rejected")
        try:
            with wave.open(str(path), "rb") as audio:
                if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (
                    16000,
                    1,
                    2,
                ):
                    raise ASRError("worker_pcm_invalid")
                if not 0 < audio.getnframes() <= request.max_duration_seconds * 16000:
                    raise ASRError("worker_duration_exceeded")
        except (OSError, wave.Error, EOFError):
            raise ASRError("worker_pcm_invalid") from None
        return path

    async def handle(self, reader, writer):
        current = asyncio.current_task()
        self.connections.add(current)
        tasks = []
        error_code, entry = None, None
        try:
            if len(self.connections) > 8:
                raise ASRError("worker_busy")
            initial = await asyncio.wait_for(read(reader), 10)
            if initial.get("fingerprint") != self.fingerprint:
                raise ASRError("worker_config_mismatch")
            op = initial.get("op")
            fields = {"op", "fingerprint"} | (
                set() if op == "health" else {"request_id"} if op == "cancel" else {"request"}
            )
            if op == "file":
                fields.add("path")
            if op not in {"file", "stream", "health", "cancel"} or set(initial) != fields:
                raise ASRError("worker_protocol_invalid")
            if op == "cancel":
                await self.cancel_request(initial["request_id"])
                await write(writer, {"type": "cancel_status", "stopped": True})
                return
            if op == "health":
                result = await asyncio.wait_for(self.provider.health(), 5)
                await write(writer, {"type": "health", "data": result.model_dump(mode="json")})
                return
            request = ASRRequest.model_validate(initial["request"])
            if request.allow_network or request.privacy != "local_only":
                raise ASRError("worker_local_only_required")
            request_id = request.request_id
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id):
                raise ASRError("worker_request_id_invalid")
            if request_id in self.requests:
                raise ASRError("worker_request_reused")
            if len(self.requests) >= 4096:
                raise ASRError("worker_busy")
            entry = {"stopped": asyncio.Event(), "task": current, "canceled": False}
            self.requests[request_id] = entry
            path = self.audio_path(initial.get("path"), request) if op == "file" else None
            queue = asyncio.Queue(maxsize=16)
            ended = False

            async def receive():
                nonlocal ended
                total = 0
                while True:
                    message = await asyncio.wait_for(
                        read(reader), 10 if not ended and op == "stream" else None
                    )
                    if message == {"type": "cancel"}:
                        raise EOFError
                    if op != "stream" or ended:
                        raise ASRError("worker_protocol_invalid")
                    if message == {"type": "end"}:
                        if not total or total % 2:
                            raise ASRError("worker_pcm_invalid")
                        ended = True
                        item = None
                    elif set(message) == {"type", "data"} and message["type"] == "pcm":
                        try:
                            item = base64.b64decode(message["data"], validate=True)
                        except (ValueError, TypeError):
                            raise ASRError("worker_pcm_invalid") from None
                        if not item or len(item) > MAX_CHUNK:
                            raise ASRError("worker_pcm_invalid")
                        total += len(item)
                        if total > request.max_duration_seconds * 32000:
                            raise ASRError("worker_duration_exceeded")
                    else:
                        raise ASRError("worker_protocol_invalid")
                    try:
                        queue.put_nowait(item)
                    except asyncio.QueueFull:
                        raise ASRError("worker_backpressure") from None

            async def chunks():
                bound = min(MAX_CHUNK, self.config.stream_window_ms * 32)
                while (chunk := await queue.get()) is not None:
                    for offset in range(0, len(chunk), bound):
                        yield chunk[offset : offset + bound]

            async def execute():
                async with asyncio.timeout(self.config.lock_timeout_seconds):
                    await self.inference.acquire()
                try:
                    if op == "file":
                        result = await self.provider.transcribe_file(path, request)
                        await write(
                            writer, {"type": "result", "data": result.model_dump(mode="json")}
                        )
                    else:
                        completed = None
                        async with aclosing(
                            self.provider.transcribe_stream(chunks(), request)
                        ) as events:
                            async for event in events:
                                if event.type == "completed":
                                    if not ended:
                                        raise ASRError("worker_response_invalid")
                                    completed = event
                                    continue
                                await write(
                                    writer, {"type": "event", "data": event.model_dump(mode="json")}
                                )
                        if completed is None:
                            raise ASRError("worker_response_invalid")
                        # Exhaust the generator first so successful EOF cannot cancel its lease.
                        await write(
                            writer, {"type": "event", "data": completed.model_dump(mode="json")}
                        )
                finally:
                    # Provider cancellation contract waits for native thread and clears bad cache.
                    self.inference.release()

            receiver, executor = asyncio.create_task(receive()), asyncio.create_task(execute())
            tasks = [receiver, executor]
            async with asyncio.timeout(
                request.max_duration_seconds + self.config.lock_timeout_seconds + 120
            ):
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:
                    await receiver
                await executor
        except (EOFError, ConnectionError, asyncio.CancelledError):
            pass
        except Exception as error:
            error_code = "worker_timeout" if isinstance(error, TimeoutError) else safe_code(error)
        finally:
            for task in tasks:
                task.cancel()
            # Do not release serial inference or unload resident models before native work stops.
            cleanup = asyncio.gather(*tasks, return_exceptions=True)
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            if entry is not None:
                entry["stopped"].set()
                entry["task"] = None
            with suppress(Exception):
                if error_code:
                    await write(writer, {"type": "error", "code": error_code})
                # Sole proof of stop: all inference tasks finished and released their locks.
                await write(writer, {"type": "stopped"})
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            self.connections.discard(current)
