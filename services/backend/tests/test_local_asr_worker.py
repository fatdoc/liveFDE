"""Real Unix RPC with explicit synthetic provider, never loads or downloads model weights."""

import asyncio
import os
import shutil
import socket
import tempfile
import wave
from pathlib import Path

import pytest
from pydantic import BaseModel

from live_review.integrations.asr_gateway.contracts import (
    ASRError,
    ASREvent,
    ASRHealth,
    ASRRequest,
    ASRResult,
    ASRSegment,
)
from live_review.integrations.asr_gateway.local_worker import LocalWorkerProvider
from live_review.integrations.asr_gateway.local_worker.protocol import fingerprint, read, write
from live_review.integrations.asr_gateway.local_worker.server import LocalWorkerServer


class Config(BaseModel):
    model_root: Path
    device: str = "cpu"
    stream_window_ms: int = 1000
    lock_timeout_seconds: int = 1


class Synthetic:
    def __init__(self):
        self.calls, self.active, self.max_active = 0, 0, 0
        self.cleaned, self.started = asyncio.Event(), asyncio.Event()
        self.block = False
        self.stream_released = False

    async def health(self):
        return ASRHealth(provider="local", ready=True, reason="synthetic")

    def result(self):
        return ASRResult(
            provider="local",
            model="synthetic",
            synthetic=True,
            source="local",
            segments=(
                ASRSegment(
                    id="0", text="合成", start_ms=0, end_ms=200, timestamp_source="provider"
                ),
            ),
            complete=True,
            duration_ms=200,
            elapsed_ms=1,
        )

    async def transcribe_file(self, path, request):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        try:
            if self.block:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    # Simulate LOCAL's shielded native-thread cleanup before lock release.
                    await asyncio.sleep(0.1)
                    self.cleaned.set()
                    raise
            return self.result()
        finally:
            self.active -= 1

    async def transcribe_stream(self, chunks, request):
        self.calls += 1
        total = 0
        async for chunk in chunks:
            assert len(chunk) <= 32000
            total += len(chunk)
            yield ASREvent(type="partial", segment=ASRSegment(id="0", text="合成", final=False))
        assert total
        result = self.result()
        yield ASREvent(type="final", segment=result.segments[0])
        yield ASREvent(type="completed", result=result)
        self.stream_released = True


@pytest.fixture
def paths():
    # Keep sockaddr below macOS's 104-byte bound, all artifacts in the approved runtime.
    parent = Path("/Users/docfat/Desktop/个人/project/直播体系FDE/runtime/live-006c")
    root = Path(tempfile.mkdtemp(prefix="w", dir=parent))
    os.chmod(root, 0o700)
    audio = root / "sample.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 3200)
    yield root, audio
    shutil.rmtree(root)


def req(**updates):
    from uuid import uuid4

    return ASRRequest(
        request_id=updates.pop("request_id", uuid4().hex), max_duration_seconds=2, **updates
    )


def test_file_health_and_single_provider_instance_reused(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            client = LocalWorkerProvider(root / "s", config)
            assert (await client.health()).network_checked is False
            assert provider.calls == 0
            assert (await client.transcribe_file(audio, req())).synthetic
            assert (await client.transcribe_file(audio, req())).complete
            assert provider.calls == 2 and server.provider is provider
            assert (root / "s").stat().st_mode & 0o777 == 0o600
        finally:
            await server.close()
        assert not (root / "s").exists()

    asyncio.run(run())


def test_stream_bounded_pcm_events_and_generator_exhausted(paths):
    root, _ = paths

    async def chunks():
        yield b"\0\0" * 32000

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            events = [
                e
                async for e in LocalWorkerProvider(root / "s", config).transcribe_stream(
                    chunks(), req()
                )
            ]
            assert [e.type for e in events] == ["partial", "partial", "final", "completed"]
            assert provider.stream_released and provider.calls == 1
        finally:
            await server.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["network", "privacy", "config", "path", "symlink"])
def test_rejects_unauthorized_configuration_and_audio(paths, failure):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            chosen = config.model_copy(update={"device": "cuda"}) if failure == "config" else config
            client = LocalWorkerProvider(root / "s", chosen)
            request = (
                req(allow_network=True)
                if failure == "network"
                else req(privacy="cloud_allowed" if failure == "privacy" else "local_only")
            )
            path = Path("/etc/passwd") if failure == "path" else audio
            if failure == "symlink":
                path = root / "link.wav"
                path.symlink_to(audio)
            with pytest.raises(ASRError) as error:
                await client.transcribe_file(path, request)
            assert str(root) not in str(error.value) and provider.calls == 0
        finally:
            await server.close()

    asyncio.run(run())


def test_server_independently_denies_network_and_bad_frames(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            for payload in [
                {
                    "op": "file",
                    "fingerprint": fingerprint(config),
                    "path": str(audio),
                    "request": req(allow_network=True).model_dump(mode="json"),
                },
                {"op": "health", "fingerprint": fingerprint(config), "device": "cuda"},
            ]:
                reader, writer = await asyncio.open_unix_connection(str(root / "s"))
                await write(writer, payload)
                response = await read(reader)
                assert response["type"] == "error"
                writer.close()
                await writer.wait_closed()
            assert provider.calls == 0
        finally:
            await server.close()

    asyncio.run(run())


def test_disconnect_waits_for_cleanup_before_next_inference(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        provider.block = True
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            client = LocalWorkerProvider(root / "s", config)
            first = asyncio.create_task(client.transcribe_file(audio, req()))
            await provider.started.wait()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            provider.block = False
            second = await client.transcribe_file(audio, req())
            assert second.complete and provider.cleaned.is_set() and provider.max_active == 1
        finally:
            await server.close()

    asyncio.run(run())


def test_existing_socket_never_replaced(paths):
    root, _ = paths
    foreign = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    foreign.bind(str(root / "s"))
    before = (root / "s").stat().st_ino

    async def run():
        with pytest.raises(ASRError, match="worker_socket_invalid"):
            await LocalWorkerServer(root / "s", Config(model_root=root), root, Synthetic()).start()
        assert (root / "s").stat().st_ino == before

    try:
        asyncio.run(run())
    finally:
        foreign.close()


def test_unavailable_and_public_socket_no_autostart(paths):
    root, audio = paths

    async def run():
        client = LocalWorkerProvider(root / "missing", Config(model_root=root))
        with pytest.raises(ASRError, match="worker_unavailable"):
            await client.transcribe_file(audio, req())
        assert not (root / "missing").exists()
        os.chmod(root, 0o755)
        with pytest.raises(ASRError, match="worker_socket_invalid"):
            await client.health()
        os.chmod(root, 0o700)

    asyncio.run(run())


def test_malformed_and_oversized_rpc_frames_rejected(paths):
    root, _ = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            for content in (b"not-json\n", b"x" * (128 * 1024 + 1) + b"\n"):
                reader, writer = await asyncio.open_unix_connection(str(root / "s"))
                writer.write(content)
                await writer.drain()
                response = await read(reader)
                assert response == {"type": "error", "code": "worker_protocol_invalid"}
                writer.close()
                await writer.wait_closed()
            assert provider.calls == 0
        finally:
            await server.close()

    asyncio.run(run())


def test_shutdown_waits_for_inference_cleanup_and_unloads(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        provider.block = True
        unloaded = []

        async def unload():
            assert provider.active == 0 and provider.cleaned.is_set()
            unloaded.append(True)

        server = await LocalWorkerServer(root / "s", config, root, provider, unload).start()
        pending = asyncio.create_task(
            LocalWorkerProvider(root / "s", config).transcribe_file(audio, req())
        )
        await provider.started.wait()
        await server.close()
        with pytest.raises(ASRError):
            await pending
        assert unloaded == [True] and not (root / "s").exists()

    asyncio.run(run())


def test_cancel_ack_waits_for_cleanup_before_return(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        provider.block = True
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            pending = asyncio.create_task(
                LocalWorkerProvider(root / "s", config).transcribe_file(audio, req())
            )
            await provider.started.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert provider.cleaned.is_set() and provider.active == 0
        finally:
            await server.close()

    asyncio.run(run())


def test_cancel_timeout_is_unknown_not_confirmed(paths, monkeypatch):
    from live_review.integrations.asr_gateway.local_worker import client as implementation

    monkeypatch.setattr(implementation, "STOP_TIMEOUT_SECONDS", 0.01)
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        provider.block = True
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            pending = asyncio.create_task(
                LocalWorkerProvider(root / "s", config).transcribe_file(audio, req())
            )
            await provider.started.wait()
            pending.cancel()
            with pytest.raises(ASRError, match="worker_stop_unconfirmed") as error:
                await pending
            assert error.value.unknown and provider.active == 1
            await provider.cleaned.wait()
        finally:
            await server.close()

    asyncio.run(run())


def test_external_cancel_active_and_late_tombstone(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        provider.block = True
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            client = LocalWorkerProvider(root / "s", config)
            pending = asyncio.create_task(client.transcribe_file(audio, req(request_id="job:1")))
            await provider.started.wait()
            await client.cancel_and_wait("job:1")
            assert provider.cleaned.is_set() and provider.active == 0
            with pytest.raises(ASRError, match="worker_canceled"):
                await pending
            await client.cancel_and_wait("job:1")  # idempotent confirmed stop
            await client.cancel_and_wait("late:1")
            provider.block = False
            with pytest.raises(ASRError, match="worker_request_reused"):
                await client.transcribe_file(audio, req(request_id="late:1"))
            assert provider.calls == 1
            assert (await client.transcribe_file(audio, req(request_id="job:2"))).complete
            await client.cancel_and_wait("job:2")  # completed request is already stopped
        finally:
            await server.close()

    asyncio.run(run())


def test_external_cancel_without_worker_is_unconfirmed(paths):
    root, _ = paths

    async def run():
        with pytest.raises(ASRError, match="worker_stop_unconfirmed") as error:
            await LocalWorkerProvider(root / "missing", Config(model_root=root)).cancel_and_wait(
                "job:1"
            )
        assert error.value.unknown

    asyncio.run(run())


def test_external_cancel_queued_request_does_not_run_it(paths):
    root, audio = paths

    async def run():
        config, provider = Config(model_root=root), Synthetic()
        provider.block = True
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:
            client = LocalWorkerProvider(root / "s", config)
            first = asyncio.create_task(client.transcribe_file(audio, req(request_id="first:1")))
            await provider.started.wait()
            second = asyncio.create_task(client.transcribe_file(audio, req(request_id="queued:1")))
            while "queued:1" not in server.requests:
                await asyncio.sleep(0)
            await client.cancel_and_wait("queued:1")
            with pytest.raises(ASRError, match="worker_canceled"):
                await second
            assert provider.calls == 1 and provider.active == 1
            await client.cancel_and_wait("first:1")
            with pytest.raises(ASRError, match="worker_canceled"):
                await first
        finally:
            await server.close()

    asyncio.run(run())


def test_stream_cancel_waits_for_native_cleanup_ack(paths):
    root, audio = paths

    class BlockingStream(Synthetic):
        async def transcribe_stream(self, chunks, request):
            async for _ in chunks:
                result = await self.transcribe_file(audio, request)
                yield ASREvent(type="completed", result=result)

    async def chunks():
        yield b"\0\0" * 3200
        await asyncio.sleep(30)

    async def run():
        config, provider = Config(model_root=root), BlockingStream()
        provider.block = True
        server = await LocalWorkerServer(root / "s", config, root, provider).start()
        try:

            async def collect():
                return [
                    e
                    async for e in LocalWorkerProvider(root / "s", config).transcribe_stream(
                        chunks(), req()
                    )
                ]

            pending = asyncio.create_task(collect())
            await provider.started.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert provider.cleaned.is_set() and provider.active == 0
        finally:
            await server.close()

    asyncio.run(run())


def test_cancel_during_partial_socket_write_waits_for_generator_finally(paths, monkeypatch):
    from live_review.integrations.asr_gateway.local_worker import server as implementation

    root, _ = paths

    class PartialProvider:
        def __init__(self):
            self.cleaned = asyncio.Event()

        async def transcribe_stream(self, chunks, request):
            try:
                async for _ in chunks:
                    yield ASREvent(
                        type="partial", segment=ASRSegment(id="0", text="合成", final=False)
                    )
            finally:
                await asyncio.sleep(0.15)
                self.cleaned.set()

    async def run():
        blocked = asyncio.Event()
        original = implementation.write

        async def slow_write(writer, value):
            if value.get("type") == "event":
                blocked.set()
                await asyncio.sleep(30)
            return await original(writer, value)

        monkeypatch.setattr(implementation, "write", slow_write)
        config, provider = Config(model_root=root), PartialProvider()
        server = await LocalWorkerServer(root / "s", config, root, provider).start()

        async def chunks():
            yield b"\0\0" * 3200
            await asyncio.sleep(30)

        async def consume():
            async for _ in LocalWorkerProvider(root / "s", config).transcribe_stream(
                chunks(), req()
            ):
                pass

        try:
            task = asyncio.create_task(consume())
            await asyncio.wait_for(blocked.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert provider.cleaned.is_set(), "stop ACK must wait for suspended generator cleanup"
            assert not server.inference.locked()
        finally:
            await server.close()

    asyncio.run(run())
