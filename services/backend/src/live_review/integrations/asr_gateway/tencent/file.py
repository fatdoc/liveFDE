import asyncio
import base64
import json
import time
import wave
from pathlib import Path

import httpx

from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.integrations.asr_gateway.tencent.config import authorize
from live_review.integrations.asr_gateway.tencent.results import file_segments, result
from live_review.integrations.asr_gateway.tencent.signing import tc3_headers


def audio_data(path, request):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 5_000_000:
        raise ASRError("tencent_file_size_limit")
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ASRError("tencent_audio_format_required")
            duration_ms = (audio.getnframes() * 1000 + 15999) // 16000
        if not 0 < duration_ms <= request.max_duration_seconds * 1000:
            raise ASRError("audio_duration_limit")
        content = path.read_bytes()
        if len(content) > 5_000_000:
            raise ASRError("tencent_file_size_limit")
        return content, duration_ms
    except (OSError, wave.Error):
        raise ASRError("invalid_audio") from None


class FileRecognizer:
    def __init__(self, config, transport=None):
        self.config, self.transport = config, transport

    async def call(self, client, action, payload, deadline):
        config = self.config
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        headers = tc3_headers(
            config.secret_id.get_secret_value(),
            config.secret_key.get_secret_value(),
            action,
            body,
            int(time.time()),
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ASRError("tencent_result_unknown", unknown=True)
        try:
            async with asyncio.timeout(remaining):
                async with client.stream(
                    "POST", "https://asr.tencentcloudapi.com/", content=body, headers=headers
                ) as response:
                    if response.status_code >= 500 or response.status_code < 200:
                        raise ASRError("tencent_result_unknown", unknown=True)
                    if response.status_code >= 300:
                        raise ASRError("tencent_http_rejected", unknown=action != "CreateRecTask")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > 2 * 1024 * 1024:
                            raise ASRError("tencent_result_unknown", unknown=True)
                        content.extend(chunk)
            decoded = json.loads(content)["Response"]
            if decoded.get("Error"):
                code = decoded["Error"].get("Code", "")
                raise ASRError(
                    "tencent_api_error",
                    unknown=action != "CreateRecTask" or str(code).startswith("InternalError"),
                )
            return decoded["Data"]
        except ASRError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError):
            raise ASRError("tencent_result_unknown", unknown=True) from None

    async def transcribe(self, path, request):
        authorize(self.config, request)
        content, duration_ms = audio_data(path, request)
        config, started = self.config, time.monotonic()
        deadline = started + config.timeout_seconds
        payload = {
            "EngineModelType": config.engine_file,
            "ChannelNum": 1,
            "ResTextFormat": 2,
            "SourceType": 1,
            "Data": base64.b64encode(content).decode(),
            "DataLen": len(content),
            "SpeakerDiarization": int(request.speaker),
            "EmotionRecognition": int(request.emotion),
            "FilterPunc": 0 if request.punctuation else 2,
            "FilterDirty": 0,
            "FilterModal": 0,
            "ConvertNumMode": 0,
        }
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
                timeout=config.io_timeout_seconds,
            ) as client:
                created = await self.call(client, "CreateRecTask", payload, deadline)
                task_id = created.get("TaskId")
                if type(task_id) is not int or task_id <= 0:
                    raise ASRError("tencent_result_unknown", unknown=True)
                for _ in range(config.max_poll_requests):
                    data = await self.call(
                        client, "DescribeTaskStatus", {"TaskId": task_id}, deadline
                    )
                    if data.get("TaskId") != task_id:
                        raise ASRError("tencent_result_unknown", unknown=True)
                    status = data.get("Status")
                    if status == 2:
                        return result(
                            config.engine_file,
                            file_segments(data, request, duration_ms),
                            request,
                            duration_ms,
                            round((time.monotonic() - started) * 1000),
                        )
                    if status == 3:
                        raise ASRError("tencent_recognition_failed")
                    if status not in {0, 1}:
                        raise ASRError("tencent_result_unknown", unknown=True)
                    await asyncio.sleep(
                        min(config.poll_interval_seconds, max(0, deadline - time.monotonic()))
                    )
                raise ASRError("tencent_result_unknown", unknown=True)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ASRError("tencent_result_unknown", unknown=True) from None
        except asyncio.CancelledError:
            raise ASRError("tencent_result_unknown", unknown=True) from None
