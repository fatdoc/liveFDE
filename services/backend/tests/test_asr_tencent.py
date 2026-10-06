import asyncio
import base64
import json
import queue
import time
import wave
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from live_review.integrations.asr_gateway.contracts import ASRError, ASRRequest
from live_review.integrations.asr_gateway.tencent import TencentASRProvider, TencentConfig
from live_review.integrations.asr_gateway.tencent.signing import realtime_url, tc3_headers


def config(**changes):
    return TencentConfig(
        app_id="123456789",
        secret_id=SecretStr("synthetic-id"),
        secret_key=SecretStr("synthetic-key"),
        engine_file="16k_zh_en_2.0",
        engine_stream="16k_zh_en_speaker_2.0",
        **changes,
    )


def request(**changes):
    args = dict(
        allow_network=True,
        privacy="cloud_allowed",
        request_id="synthetic-request",
        max_duration_seconds=2,
    )
    args.update(changes)
    return ASRRequest(**args)


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "synthetic.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 6400)
    return path


def test_signatures_bind_payload_and_v2_path():
    headers = tc3_headers("synthetic-id", "synthetic-key", "CreateRecTask", b"{}", 1700000000)
    assert headers["Authorization"].startswith(
        "TC3-HMAC-SHA256 Credential=synthetic-id/2023-11-14/asr/tc3_request"
    )
    assert headers["X-TC-Version"] == "2019-06-14"
    assert (
        headers["Authorization"]
        != tc3_headers(
            "synthetic-id", "synthetic-key", "CreateRecTask", b'{"DataLen":1}', 1700000000
        )["Authorization"]
    )
    params = {"voice_id": "voice-id", "timestamp": 1700000000, "secretid": "synthetic-id"}
    signed = realtime_url("123456789", "synthetic-key", params)
    assert urlsplit(signed).path == "/asr/v2/123456789"
    assert "/asr/v1/" not in signed
    import hashlib
    import hmac

    material = (
        "asr.cloud.tencent.com/asr/v2/123456789?secretid=synthetic-id"
        "&timestamp=1700000000&voice_id=voice-id"
    )
    expected = base64.b64encode(
        hmac.new(b"synthetic-key", material.encode(), hashlib.sha1).digest()
    )
    assert parse_qs(urlsplit(signed).query)["signature"] == [expected.decode()]


def test_file_submit_poll_success_and_fields(wav):
    calls = []

    def handle(req):
        payload = json.loads(req.content)
        calls.append((req.headers["x-tc-action"], payload))
        if len(calls) == 1:
            assert req.url == "https://asr.tencentcloudapi.com/"
            assert payload["DataLen"] == len(base64.b64decode(payload["Data"]))
            assert base64.b64decode(payload["Data"]) == wav.read_bytes()
            assert payload["SpeakerDiarization"] == 1 and payload["EmotionRecognition"] == 1
            return httpx.Response(200, json={"Response": {"Data": {"TaskId": 42}}})
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Data": {
                        "TaskId": 42,
                        "Status": 2,
                        "ResultDetail": [
                            {
                                "FinalSentence": "合成转录响应",
                                "StartMs": 0,
                                "EndMs": 400,
                                "SpeakerId": 0,
                                "EmotionType": ["happy"],
                            }
                        ],
                    }
                }
            },
        )

    result = asyncio.run(
        TencentASRProvider(config(), http_transport=httpx.MockTransport(handle)).transcribe_file(
            wav, request(speaker=True, emotion=True)
        )
    )
    assert result.complete and result.source == "cloud" and not result.synthetic
    assert result.segments[0].speaker_id == "0" and result.segments[0].speaker_name is None
    assert result.segments[0].emotion == "happy" and result.segments[0].emotion_confidence is None
    assert [action for action, _ in calls] == ["CreateRecTask", "DescribeTaskStatus"]


@pytest.mark.parametrize("changes", [{"allow_network": False}, {"privacy": "local_only"}])
def test_file_privacy_and_authorization_before_transport(wav, changes):
    calls = []
    provider = TencentASRProvider(
        config(), http_transport=httpx.MockTransport(lambda req: calls.append(req))
    )
    with pytest.raises(ASRError, match="cloud_not_authorized"):
        asyncio.run(provider.transcribe_file(wav, request(**changes)))
    assert not calls


def test_file_unknown_not_resubmitted_and_safe_error(wav):
    calls = []

    def handle(req):
        calls.append(req)
        raise httpx.ReadTimeout("secret-sensitive-synthetic-error", request=req)

    with pytest.raises(ASRError) as raised:
        asyncio.run(
            TencentASRProvider(
                config(), http_transport=httpx.MockTransport(handle)
            ).transcribe_file(wav, request())
        )
    assert raised.value.unknown and len(calls) == 1
    assert "sensitive" not in str(raised.value) and raised.value.__suppress_context__


@pytest.mark.parametrize("status", [0, 1, 3])
def test_file_pending_timeout_and_terminal_error(wav, status):
    calls = []

    def handle(req):
        action = req.headers["x-tc-action"]
        calls.append(action)
        data = {"TaskId": 42} if action == "CreateRecTask" else {"TaskId": 42, "Status": status}
        return httpx.Response(200, json={"Response": {"Data": data}})

    with pytest.raises(ASRError) as raised:
        asyncio.run(
            TencentASRProvider(
                config(max_poll_requests=1, poll_interval_seconds=0.1),
                http_transport=httpx.MockTransport(handle),
            ).transcribe_file(wav, request())
        )
    assert raised.value.unknown == (status != 3)
    assert calls == ["CreateRecTask", "DescribeTaskStatus"]


def test_file_missing_timestamps_preserves_text_not_complete(wav):
    def handle(req):
        data = {"TaskId": 42}
        if req.headers["x-tc-action"] != "CreateRecTask":
            data |= {"Status": 2, "Result": "已知原文没有时间戳"}
        return httpx.Response(200, json={"Response": {"Data": data}})

    result = asyncio.run(
        TencentASRProvider(config(), http_transport=httpx.MockTransport(handle)).transcribe_file(
            wav, request()
        )
    )
    assert not result.complete and result.segments[0].text == "已知原文没有时间戳"
    assert result.segments[0].start_ms is None


class FakeWebsocket:
    def __init__(self, url, **options):
        self.voice_id = parse_qs(urlsplit(url).query)["voice_id"][0]
        self.messages, self.parts, self.times = queue.Queue(), [], []
        self.closed, self.options = False, options
        self.messages.put(json.dumps({"code": 0, "voice_id": self.voice_id}))

    def send_binary(self, part):
        self.parts.append(part)
        self.times.append(time.monotonic())
        self.messages.put(
            json.dumps(
                {
                    "code": 0,
                    "voice_id": self.voice_id,
                    "sentences": {
                        "sentence_list": [
                            {
                                "sentence_id": 0,
                                "sentence": "合成响应",
                                "sentence_type": 0,
                                "speaker_id": -1,
                                "start_time": 0,
                                "end_time": 200,
                            }
                        ]
                    },
                }
            )
        )

    def send(self, text):
        assert json.loads(text) == {"type": "end"}
        self.messages.put(
            json.dumps(
                {
                    "code": 0,
                    "voice_id": self.voice_id,
                    "sentences": {
                        "sentence_list": [
                            {
                                "sentence_id": 0,
                                "sentence": "合成响应最终态",
                                "sentence_type": 1,
                                "speaker_id": 2,
                                "start_time": 0,
                                "end_time": 400,
                            }
                        ]
                    },
                }
            )
        )
        self.messages.put(json.dumps({"code": 0, "voice_id": self.voice_id, "final": 1}))

    def recv(self):
        return self.messages.get(timeout=1)

    def close(self):
        self.closed = True
        self.messages.put("")


async def pcm_chunks():
    yield b"\0\0" * 6400


def test_stream_v2_concurrent_results_pacing_and_end():
    sockets, urls = [], []

    def connector(url, timeout):
        urls.append(url)
        ws = FakeWebsocket(url, timeout=timeout)
        sockets.append(ws)
        return ws

    async def run():
        return [
            event
            async for event in TencentASRProvider(config(), ws_connect=connector).transcribe_stream(
                pcm_chunks(), request(speaker=True)
            )
        ]

    events = asyncio.run(run())
    assert sockets[0].closed and len(sockets[0].parts) == 2
    assert sockets[0].times[1] - sockets[0].times[0] >= 0.19
    assert events[0].segment.speaker_id is None and not events[0].segment.final
    assert events[-1].type == "completed" and events[-1].result.complete
    assert events[-1].result.segments[0].speaker_id == "2"
    assert events[-1].result.segments[0].speaker_name is None
    assert parse_qs(urlsplit(urls[0]).query)["result_mod"] == ["1"]
    assert "/asr/v2/" in urls[0]


def test_stream_emotion_rejected_without_connect_and_health_not_network():
    calls = []
    provider = TencentASRProvider(config(), ws_connect=lambda *args: calls.append(args))

    async def run():
        with pytest.raises(ASRError, match="stream_emotion_not_supported"):
            async for _ in provider.transcribe_stream(pcm_chunks(), request(emotion=True)):
                pass
        health = await provider.health()
        assert health.ready and not health.network_checked

    asyncio.run(run())
    assert not calls and "synthetic-key" not in config().model_dump_json() + repr(config())


def test_stream_disconnect_unknown_and_never_reconnect():
    sockets = []

    class Broken(FakeWebsocket):
        def send_binary(self, part):
            self.parts.append(part)
            self.messages.put("")

    def connect(url, timeout):
        ws = Broken(url)
        sockets.append(ws)
        return ws

    async def run():
        with pytest.raises(ASRError) as raised:
            async for _ in TencentASRProvider(config(), ws_connect=connect).transcribe_stream(
                pcm_chunks(), request()
            ):
                pass
        assert raised.value.unknown

    asyncio.run(run())
    assert len(sockets) == 1 and sockets[0].closed


@pytest.mark.parametrize("mode", ["stalled", "failure"])
def test_stream_sender_supervision_closes_blocked_receive(mode):
    sockets = []

    class Waiting(FakeWebsocket):
        def recv(self):
            return self.messages.get(timeout=2)

    def connect(url, timeout):
        ws = Waiting(url)
        sockets.append(ws)
        return ws

    async def chunks():
        if mode == "failure":
            raise RuntimeError("private-input-details")
        await asyncio.sleep(10)
        yield b"\0\0"

    async def run():
        with pytest.raises(ASRError) as raised:
            async for _ in TencentASRProvider(
                config(timeout_seconds=0.15), ws_connect=connect
            ).transcribe_stream(chunks(), request()):
                pass
        assert raised.value.unknown and "private" not in str(raised.value)

    started = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - started < 1 and sockets[0].closed


def test_stream_direct_sentence_protocol_shape():
    class Direct(FakeWebsocket):
        def recv(self):
            value = json.loads(super().recv())
            if "sentences" in value:
                value["sentences"] = value["sentences"]["sentence_list"][0]
            return json.dumps(value)

    async def run():
        return [
            event
            async for event in TencentASRProvider(
                config(), ws_connect=lambda url, timeout: Direct(url)
            ).transcribe_stream(pcm_chunks(), request(speaker=True))
        ]

    events = asyncio.run(run())
    assert events[-1].result.complete and events[-1].result.segments[0].speaker_id == "2"


def test_oversized_local_file_rejected_before_network(tmp_path):
    path = tmp_path / "oversized.wav"
    with path.open("wb") as output:
        output.truncate(5_000_001)
    calls = []
    provider = TencentASRProvider(
        config(), http_transport=httpx.MockTransport(lambda req: calls.append(req))
    )
    with pytest.raises(ASRError):
        asyncio.run(provider.transcribe_file(path, request()))
    assert not calls


def test_stream_cancel_closes_socket_and_reports_unknown():
    sockets = []

    def connect(url, timeout):
        ws = FakeWebsocket(url)
        sockets.append(ws)
        return ws

    async def chunks():
        await asyncio.sleep(10)
        yield b"\0\0"

    async def consume():
        async for _ in TencentASRProvider(config(), ws_connect=connect).transcribe_stream(
            chunks(), request()
        ):
            pass

    async def run():
        task = asyncio.create_task(consume())
        while not sockets:
            await asyncio.sleep(0.001)
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(ASRError) as raised:
            await task
        assert raised.value.unknown

    asyncio.run(run())
    assert sockets[0].closed


def test_stream_cancel_during_connect_closes_eventual_socket():
    sockets = []

    def connect(url, timeout):
        time.sleep(0.05)
        ws = FakeWebsocket(url)
        sockets.append(ws)
        return ws

    async def consume():
        async for _ in TencentASRProvider(config(), ws_connect=connect).transcribe_stream(
            pcm_chunks(), request()
        ):
            pass

    async def run():
        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(ASRError) as raised:
            await task
        assert raised.value.unknown

    asyncio.run(run())
    assert len(sockets) == 1 and sockets[0].closed
