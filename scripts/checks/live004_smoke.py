"""Real HTTP/restart and additive migration smoke on LIVE-004 integration DB only."""

import hashlib
import io
import json
import os
import secrets
import socket
import subprocess
import time
import wave
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
RUNTIME = WORKSPACE / "runtime/live-004"
PORT = 8194
ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}


def main():
    if ROOT != Path("/Users/docfat/Desktop/个人/project/直播体系FDE/app"):
        raise SystemExit("Run integrated smoke from the registered product checkout")
    environment = os.environ.copy()
    for line in (RUNTIME / "integration.env").read_text().splitlines():
        key, value = line.split("=", 1)
        environment[key] = value
    url = urlsplit(environment["LIVE_DATABASE_URL"])
    if (
        (url.scheme, url.hostname, url.port, url.username, url.path)
        != (
            "postgresql+psycopg",
            "127.0.0.1",
            15440,
            "live004_integration",
            "/live004_integration",
        )
        or url.query
        or url.fragment
    ):
        raise SystemExit("Refusing non-integration database")
    storage = Path(environment["LIVE_STORAGE_ROOT"])
    if storage.resolve() != RUNTIME / "storage-integration":
        raise SystemExit("Refusing non-integration storage")
    # Explicit development test settings; no external service or inherited production auth.
    environment.update(
        LIVE_ENVIRONMENT="development",
        LIVE_TRUSTED_ORIGINS=json.dumps(["http://127.0.0.1:5188"]),
        LIVE_LOGIN_LIMIT="100",
        LIVE_LOGIN_WINDOW_SECONDS="60",
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    backend = ROOT / "services/backend"
    python = str(backend / ".venv/bin/python")
    evidence = {"synthetic": True, "port": PORT, "checks": []}
    process = None
    log = (RUNTIME / "integration-api.log").open("w")

    def command(*args, input=None):
        result = subprocess.run(
            [python, *args],
            cwd=backend,
            env=environment,
            input=input,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                "Integration subprocess failed; no secret output emitted"
            )

    def migrate(target):
        command("-m", "alembic", "upgrade", target)

    def start():
        nonlocal process
        process = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "live_review.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
            ],
            cwd=backend,
            env=environment,
            stdout=log,
            stderr=log,
        )
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("API process exited")
            try:
                if (
                    httpx.get(
                        f"http://127.0.0.1:{PORT}/health/live",
                        timeout=1,
                        trust_env=False,
                    ).status_code
                    == 200
                ):
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        raise RuntimeError("API startup timeout")

    def stop():
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def bootstrap(label):
        username, password = "smoke-" + uuid4().hex, secrets.token_urlsafe(32)
        command(
            "-m",
            "live_review.modules.identity.cli",
            "--username",
            username,
            "--display-name",
            label,
            "--workspace-name",
            "Synthetic LIVE-004 smoke",
            "--password-stdin",
            input=password + "\n",
        )
        return username, password

    def login(client, account):
        response = client.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"username": account[0], "password": account[1]},
        )
        assert response.status_code == 200
        return ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}

    try:
        engine = create_engine(environment["LIVE_DATABASE_URL"])
        with engine.connect() as connection:
            fresh = (
                connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
                is None
            )
        engine.dispose()
        migrate("0001_identity" if fresh else "head")
        account = bootstrap("Primary fixture")
        migrate("0002_sessions" if fresh else "head")
        start()
        with httpx.Client(
            base_url=f"http://127.0.0.1:{PORT}", timeout=30, trust_env=False
        ) as client:
            headers = login(client, account)
            streamer = client.post(
                "/api/v1/streamers",
                headers=headers,
                json={"name": "真实API合成主播", "platform": "douyin"},
            )
            assert streamer.status_code == 201
            response = client.post(
                "/api/v1/sessions",
                headers=headers,
                json={
                    "streamer_id": streamer.json()["id"],
                    "title": "合成录像测试",
                    "platform": "douyin",
                    "session_local_date": "2026-10-05",
                },
            )
            assert response.status_code == 201
            session_id = response.json()["id"]
            assert response.json()["started_at"] is None
            stop()
            migrate("head")
            start()
            assert client.get("/api/v1/auth/me").status_code == 200
            assert (
                client.get(f"/api/v1/sessions/{session_id}").json()["title"]
                == "合成录像测试"
            )
            evidence["checks"].append(
                "cookie/admin/session survive API restart and final migration"
            )
            evidence["fresh_A_to_B_to_C_upgrade"] = fresh
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\0\0" * 800)
            payload = buffer.getvalue()
            digest = hashlib.sha256(payload).hexdigest()
            initialize = client.post(
                "/api/v1/materials/uploads",
                headers=headers | {"Idempotency-Key": uuid4().hex},
                json={
                    "filename": "synthetic.wav",
                    "byte_size": len(payload),
                    "media_type": "audio/wav",
                    "purpose": "session_media",
                    "sha256": digest,
                },
            )
            assert initialize.status_code == 201, initialize.status_code
            upload_id = initialize.json()["upload_id"]
            upload_url = f"/api/v1/materials/uploads/{upload_id}"
            assert (
                client.post(upload_url + "/finalize", headers=headers).status_code
                == 409
            )
            assert (
                client.put(
                    upload_url + "/content", headers=headers, content=payload
                ).status_code
                == 200
            )
            result = client.post(upload_url + "/finalize", headers=headers)
            assert result.status_code == 200, result.status_code
            material_id = result.json()["material_id"]
            assert result.json()["sha256"] == digest
            assert (
                client.post(upload_url + "/finalize", headers=headers).json()[
                    "material_id"
                ]
                == material_id
            )
            link = f"/api/v1/sessions/{session_id}/materials"
            body = {"material_id": material_id, "role": "primary"}
            assert client.post(link, headers=headers, json=body).status_code == 201
            assert (
                client.post(link, headers=headers, json=body).json()["already_linked"]
                is True
            )
            content_url = f"/api/v1/materials/{material_id}/content"
            assert (
                client.get(content_url, headers={"Range": "bytes=0-9"}).content
                == payload[:10]
            )
            assert (
                client.get(content_url, headers={"Range": "bytes=999999-"}).status_code
                == 416
            )
            head = client.head(content_url)
            assert head.status_code == 200 and int(
                head.headers["content-length"]
            ) == len(payload)
            assert (
                client.get(
                    content_url, headers={"Range": "bytes=0-9", "If-Range": '"other"'}
                ).status_code
                == 200
            )
            second = bootstrap("Other workspace fixture")
            with httpx.Client(base_url=client.base_url, trust_env=False) as other:
                denied = other.get(content_url, headers={"Range": "bytes=0-9"})
                assert denied.status_code == 401 and "etag" not in denied.headers
                login(other, second)
                denied = other.get(content_url, headers={"Range": "bytes=0-9"})
                assert denied.status_code == 404 and "etag" not in denied.headers
            stop()
            start()
            readback = client.get(content_url)
            assert readback.status_code == 200 and readback.content == payload
            assert hashlib.sha256(readback.content).hexdigest() == digest
            assert (
                client.post("/api/v1/auth/logout", headers=headers).status_code == 204
            )
            assert client.get(content_url).status_code == 401
            evidence["checks"].append(
                "real WAV upload/finalize/association/range/auth/restart bytes match"
            )
            evidence["material_sha256"] = digest
            evidence["checks"].append("logout revokes persisted cookie")
        (RUNTIME / "integration-results.json").write_text(
            json.dumps(evidence, indent=2)
        )
        print(json.dumps(evidence, indent=2))
    finally:
        stop()
        log.close()


if __name__ == "__main__":
    main()
