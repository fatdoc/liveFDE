"""Explicit real local smoke on a public sample; never permits a cloud provider."""

import hashlib
import json
import time
import wave
from uuid import uuid4

import httpx
import websocket
from live006c_preview import private_read
from live006c_runtime import RUNTIME


def main():
    account = json.loads(private_read("ui-account.json"))
    audio = RUNTIME / "public-zh-16k.wav"
    raw = audio.read_bytes()
    run = RUNTIME / "smoke" / uuid4().hex
    run.mkdir(parents=True, mode=0o700)
    observations = {
        "sample_sha256": hashlib.sha256(raw).hexdigest(),
        "synthetic": False,
        "cloud_policy": "local_only_no_cloud_grant",
        "network_audit": "not_instrumented_by_this_script",
        "file_runs": [],
    }
    with httpx.Client(
        base_url="http://127.0.0.1:8196/api/v1",
        timeout=30,
        trust_env=False,
        headers={"Origin": "http://127.0.0.1:5196"},
    ) as client:

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.is_error:
                raise RuntimeError(f"smoke_api_failed:{response.status_code}:{path}")
            return response.json() if response.content else None

        login = call(
            "POST",
            "/auth/login",
            json={key: account[key] for key in ("username", "password")},
        )
        client.headers["X-CSRF-Token"] = login["csrf_token"]
        saved = call("GET", "/asr/settings")
        settings = call(
            "PUT",
            "/asr/settings",
            json={
                "expected_revision": saved["revision"],
                "provider": "local",
                "privacy": "local_only",
                "speaker": True,
                "emotion": True,
                "punctuation": True,
                "allow_cloud_fallback": False,
            },
        )
        observations["settings_revision"] = settings["revision"]
        observations["health"] = call("GET", "/asr/health")
        assert observations["health"]["health"]["ready"]
        for _ in range(2):
            started = time.monotonic()
            upload = call(
                "POST",
                "/materials/uploads",
                headers={"Idempotency-Key": uuid4().hex},
                json={
                    "filename": "public-zh-16k.wav",
                    "byte_size": len(raw),
                    "media_type": "audio/wav",
                    "purpose": "session_media",
                },
            )
            call(
                "PUT",
                f"/materials/uploads/{upload['upload_id']}/content",
                content=raw,
                headers={"Content-Type": "application/octet-stream"},
            )
            material = call(
                "POST", f"/materials/uploads/{upload['upload_id']}/finalize"
            )
            job = call(
                "POST",
                "/asr/transcriptions",
                json={
                    "material_id": material["material_id"],
                    "expected_revision": settings["revision"],
                    "allow_network": False,
                },
            )
            while time.monotonic() - started < 240:
                result = call("GET", f"/asr/transcriptions/{job['id']}")
                if result["job"]["status"] in {"succeeded", "failed", "canceled"}:
                    break
                time.sleep(1)
            observation = {
                "wall_seconds": round(time.monotonic() - started, 3),
                **result,
            }
            observations["file_runs"].append(observation)
            (run / "observations.json").write_text(
                json.dumps(observations, ensure_ascii=False, indent=2)
            )
            assert result["job"]["status"] == "succeeded", result["job"]["error"]
            assert (
                result["result"]["source"] == "local"
                and not result["result"]["synthetic"]
            )

        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        ws = websocket.create_connection(
            "ws://127.0.0.1:8196/api/v1/asr/stream",
            origin="http://127.0.0.1:5196",
            cookie=cookie,
            timeout=180,
            http_no_proxy=["*"],
        )
        started = time.monotonic()
        events = []
        try:
            ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "csrf_token": login["csrf_token"],
                        "expected_revision": settings["revision"],
                        "allow_network": False,
                    }
                )
            )
            first = json.loads(ws.recv())
            assert first["type"] == "started", first
            events.append(first)
            with wave.open(str(audio)) as source:
                assert source.getframerate() == 16000 and source.getnchannels() == 1
                assert source.getsampwidth() == 2
                # Send five seconds, then wait for the real first partial before sending EOF.
                pcm = source.readframes(16000 * 5)
                for offset in range(0, len(pcm), 6400):
                    ws.send_binary(pcm[offset : offset + 6400])
                    time.sleep(0.2)
                event = json.loads(ws.recv())
                events.append(event)
                assert event["type"] == "partial", event
                observations["stream_first_partial_before_eof"] = True
                observations["stream_first_partial_seconds"] = round(
                    time.monotonic() - started, 3
                )
                tail = source.readframes(16000)
                ws.send_binary(tail)
            ws.send(json.dumps({"type": "end"}))
            while True:
                event = json.loads(ws.recv())
                events.append(event)
                if event["type"] in {"completed", "error"}:
                    break
            observations["stream"] = {
                "wall_seconds": round(time.monotonic() - started, 3),
                "events": events,
            }
            (run / "observations.json").write_text(
                json.dumps(observations, ensure_ascii=False, indent=2)
            )
            assert events[-1]["type"] == "completed", events[-1]
            persisted = call("GET", f"/asr/transcriptions/{first['job_id']}")
            assert persisted["job"]["status"] == "succeeded"
            assert persisted["result"] == events[-1]["result"]
        finally:
            ws.close()
    print(json.dumps({"passed": True, "evidence": str(run / "observations.json")}))


if __name__ == "__main__":
    main()
