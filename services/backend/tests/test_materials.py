"""Real PG + actual synthetic formats; no provider, no binary fixtures in Git."""

import hashlib
import io
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from materials_fixture import ORIGIN, PASSWORD, init, upload, wav_bytes
from materials_fixture import materials as materials
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.core.errors import ApiError
from live_review.main import app
from live_review.modules.materials.models import Blob, Upload
from live_review.modules.materials.service import claim, locked_lease


def test_complete_dedup_idempotency_and_association(materials):
    client, headers, _, sessions, stranger = materials
    data = "真实合成逐字稿，没有时间戳。".encode()
    first = init(client, headers, data, key="durable-key")
    assert init(client, headers, data, key="durable-key").json() == first.json()
    assert init(client, headers, data + b"!", key="durable-key").status_code == 409
    uid, done = upload(client, headers, data)
    assert not done["deduplicated"]
    assert client.post(f"/api/v1/materials/uploads/{uid}/finalize", headers=headers).json() == done
    assert (
        client.put(
            f"/api/v1/materials/uploads/{uid}/content", headers=headers, content=data
        ).status_code
        == 409
    )
    _, duplicate = upload(client, headers, data)
    assert duplicate["deduplicated"]
    for session in sessions:
        path = f"/api/v1/sessions/{session.id}/materials"
        body = {"material_id": done["material_id"], "role": "primary"}
        assert client.post(path, headers=headers, json=body).status_code == 201
        repeat = client.post(path, headers=headers, json=body)
        assert repeat.status_code == 200 and repeat.json()["already_linked"]
        with TestClient(app) as reconnected:
            reconnected.cookies.update(dict(client.cookies))
            listing = reconnected.get(path).json()
            assert listing["total"] == 1 and len(listing["items"]) == 1
            assert listing["items"][0]["material"]["material_id"] == done["material_id"]
            assert reconnected.get(path + "?limit=1&offset=1").json()["items"] == []
    with Session(app.state.engine) as db:
        assert db.scalar(select(Blob).where(Blob.sha256 == done["sha256"])) is not None
    client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": stranger.username, "password": PASSWORD},
    )
    assert client.get(f"/api/v1/sessions/{sessions[0].id}/materials").status_code == 404


def test_ranges_authorization_and_restart(materials):
    client, headers, _, _, stranger = materials
    data = b"synthetic transcript 0123456789"
    _, done = upload(client, headers, data)
    path = f"/api/v1/materials/{done['material_id']}/content"
    full = client.get(path)
    assert full.status_code == 200 and full.content == data
    for value, expected in [
        ("bytes=0-3", data[:4]),
        ("bytes=5-", data[5:]),
        ("bytes=-4", data[-4:]),
    ]:
        response = client.get(path, headers={"Range": value})
        assert response.status_code == 206 and response.content == expected
    head = client.head(path, headers={"Range": "bytes=0-3"})
    assert (
        head.status_code == 200
        and head.content == b""
        and head.headers["content-length"] == str(len(data))
    )
    unavailable = client.get(path, headers={"Range": "bytes=999-"})
    assert unavailable.status_code == 416
    assert unavailable.headers["content-range"] == f"bytes */{len(data)}"
    assert client.head(path, headers={"Range": "invalid"}).status_code == 200
    assert client.get(path, headers={"Range": "wat"}).status_code == 400
    assert client.get(path, headers={"Range": "bytes=0-1,3-4"}).content == data
    assert client.get(path, headers={"Range": "bytes=0-3", "If-Range": '"old"'}).status_code == 200
    assert (
        client.get(
            path, headers={"Range": "bytes=0-3", "If-Range": full.headers["etag"]}
        ).status_code
        == 206
    )
    cookie = dict(client.cookies)
    # Fresh lifespan/engine, same DB/session token and immutable bytes.
    with TestClient(app) as restarted:
        restarted.cookies.update(cookie)
        assert restarted.get(path).content == data
    client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": stranger.username, "password": PASSWORD},
    )
    for value in ["bytes=0-3", "wat", "bytes=999-"]:
        response = client.get(path, headers={"Range": value})
        assert response.status_code == 404
        assert "etag" not in response.headers and "content-range" not in response.headers
    client.cookies.clear()
    assert client.head(path, headers={"Range": "wat"}).status_code == 401


def test_actual_formats_and_reference_boundary(materials):
    from pypdf import PdfWriter

    client, headers, _, sessions, _ = materials
    _, wav = upload(client, headers, wav_bytes(), "audio/wav", "session_media")
    assert wav["size_bytes"] > 0
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    _, pdf = upload(client, headers, output.getvalue(), "application/pdf", "reference_pdf")
    metadata = client.get(f"/api/v1/materials/{pdf['material_id']}").json()
    assert metadata["purpose"] == "reference_pdf" and not metadata["is_speech_evidence"]
    assert (
        client.post(
            f"/api/v1/sessions/{sessions[0].id}/materials",
            headers=headers,
            json={"material_id": pdf["material_id"], "role": "primary"},
        ).status_code
        == 422
    )
    root = app.state.settings.storage_root.parent / "fixtures-4c"
    root.mkdir(exist_ok=True)
    for extension, source, codec, media_type in [
        ("mp3", "sine=frequency=440:duration=0.15", "libmp3lame", "audio/mpeg"),
        ("mp4", "color=c=black:s=64x64:d=0.2", "libx264", "video/mp4"),
    ]:
        path = root / f"{uuid4()}.{extension}"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                source,
                "-c:a" if extension == "mp3" else "-c:v",
                codec,
                str(path),
            ],
            check=True,
            timeout=20,
        )
        upload(client, headers, path.read_bytes(), media_type, "session_media")


@pytest.mark.parametrize(
    "data,media_type,purpose",
    [
        (b"not a pdf", "application/pdf", "reference_pdf"),
        (b"fake wav", "audio/wav", "session_media"),
        (b"#EXTM3U\n#EXTINF:5,\nhttp://127.0.0.1:1/never-request\n", "video/mp4", "session_media"),
        (b"\xff\xfe", "text/plain", "transcript"),
        (b"  \n", "text/plain", "transcript"),
    ],
)
def test_invalid_actual_format(materials, data, media_type, purpose, monkeypatch):
    client, headers, *_ = materials
    original_run = subprocess.run
    probes = []

    def inspect_probe(command, **kwargs):
        if command[0] == app.state.settings.ffprobe_path:
            assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"
            assert command[command.index("-f") + 1] in {"mov", "mp3", "wav"}
            probes.append(command)
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", inspect_probe)
    uid = init(client, headers, data, media_type, purpose).json()["upload_id"]
    assert (
        client.put(
            f"/api/v1/materials/uploads/{uid}/content", headers=headers, content=data
        ).status_code
        == 200
    )
    assert client.post(
        f"/api/v1/materials/uploads/{uid}/finalize", headers=headers
    ).status_code in {415, 422}
    if purpose == "session_media":
        assert probes


def test_length_hash_size_and_retry(materials):
    client, headers, *_ = materials
    data = b"synthetic bytes"
    uid = init(client, headers, data).json()["upload_id"]
    path = f"/api/v1/materials/uploads/{uid}"
    assert (
        client.put(
            path + "/content", headers=headers | {"Content-Length": "1"}, content=data
        ).status_code
        == 422
    )
    assert (
        client.put(
            path + "/content",
            headers=headers | {"Content-Length": str(len(data))},
            content=b"short",
        ).status_code
        == 422
    )
    assert client.put(path + "/content", headers=headers, content=data).status_code == 200
    assert client.post(path + "/finalize", headers=headers).status_code == 200
    bad = init(client, headers, data, sha256="0" * 64).json()["upload_id"]
    client.put(f"/api/v1/materials/uploads/{bad}/content", headers=headers, content=data)
    assert (
        client.post(f"/api/v1/materials/uploads/{bad}/finalize", headers=headers).status_code == 422
    )
    assert (
        init(client, headers, data, byte_size=app.state.settings.upload_max_bytes + 1).status_code
        == 413
    )
    assert init(client, headers, data, url="https://example.invalid/media").status_code == 422


def test_persistent_concurrent_idempotency(materials):
    client, headers, *_ = materials
    key = str(uuid4())

    def request():
        return init(client, headers, b"concurrent", key=key)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: request(), range(4)))
    assert all(response.status_code == 201 for response in results), [r.text for r in results]
    assert len({r.json()["upload_id"] for r in results}) == 1
    assert init(client, headers, b"different", key=key).status_code == 409


def test_lease_takeover_and_expiration(materials):
    client, headers, admin, *_ = materials
    uid = UUID(init(client, headers, b"lease-test").json()["upload_id"])
    with Session(app.state.engine, expire_on_commit=False) as db:
        _, old = claim(db, uid, admin, "receiving", app.state.settings)
    assert (
        client.put(
            f"/api/v1/materials/uploads/{uid}/content", headers=headers, content=b"lease-test"
        ).status_code
        == 409
    )
    with Session(app.state.engine, expire_on_commit=False) as db:
        record = db.get(Upload, uid)
        record.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        _, new = claim(db, uid, admin, "receiving", app.state.settings)
        assert new != old
        with pytest.raises(ApiError) as lost:
            locked_lease(db, uid, admin, old)
        assert lost.value.code == "upload_lease_lost"
        db.rollback()
        record = db.get(Upload, uid)
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert (
        client.put(
            f"/api/v1/materials/uploads/{uid}/content", headers=headers, content=b"lease-test"
        ).status_code
        == 410
    )


def test_finalize_db_failure_keeps_recoverable_bytes(materials, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    client, headers, *_ = materials
    data = b"survive transaction failure"
    uid = init(client, headers, data).json()["upload_id"]
    path = f"/api/v1/materials/uploads/{uid}"
    client.put(path + "/content", headers=headers, content=data)
    original = Session.commit
    failed = False

    def fail_once(db):
        nonlocal failed
        if not failed and any(
            isinstance(obj, Upload) and obj.status == "available"
            for obj in db.identity_map.values()
        ):
            failed = True
            raise SQLAlchemyError("synthetic commit failure")
        return original(db)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_once)
        response = client.post(path + "/finalize", headers=headers)
        assert response.status_code == 503, response.text
    assert failed
    retry = client.post(path + "/finalize", headers=headers)
    assert retry.status_code == 200, retry.text
    assert client.get(f"/api/v1/materials/{retry.json()['material_id']}/content").content == data


def test_new_api_process_reads_original_bytes(materials):
    import socket
    import time

    import httpx

    client, headers, *_ = materials
    data = b"bytes remain identical after a real API process restart"
    _, completed = upload(client, headers, data)
    path = f"/api/v1/materials/{completed['material_id']}/content"
    runtime = app.state.settings.storage_root.parent / "fixtures-4c"
    runtime.mkdir(exist_ok=True)
    command = (
        "from live_review.main import app; "
        "from live_review.modules.materials.router import router; "
        "app.include_router(router,prefix='/api/v1'); "
        "import uvicorn,sys; uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[1]))"
    )
    pids = []
    for run in range(2):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with (runtime / f"restart-{run}.log").open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-c", command, str(port)],
                stdout=log,
                stderr=log,
                env=os.environ.copy(),
            )
            pids.append(process.pid)
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}",
                    timeout=3,
                    cookies=dict(client.cookies),
                    trust_env=False,
                ) as remote:
                    for _ in range(50):
                        try:
                            if remote.get("/health/live").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.1)
                    else:
                        pytest.fail("API process did not become live")
                    response = remote.get(path)
                    assert response.status_code == 200 and response.content == data
                    assert response.headers["etag"] == f'"{hashlib.sha256(data).hexdigest()}"'
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    assert pids[0] != pids[1]


def test_stale_identity_map_cannot_reclaim_or_fail_new_lease(materials):
    from live_review.modules.materials.service import record_failure

    client, headers, admin, *_ = materials
    uid = UUID(init(client, headers, b"takeover").json()["upload_id"])
    with Session(app.state.engine, expire_on_commit=False) as old_db:
        held, old_token = claim(old_db, uid, admin, "receiving", app.state.settings)
        assert held.lease_token == old_token
        with Session(app.state.engine, expire_on_commit=False) as newer:
            row = newer.get(Upload, uid)
            row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
            newer.commit()
            _, new_token = claim(newer, uid, admin, "receiving", app.state.settings)
        with pytest.raises(ApiError) as error:
            locked_lease(old_db, uid, admin, old_token)
        assert error.value.code == "upload_lease_lost"
        old_db.rollback()
        record_failure(old_db, uid, admin, old_token, "stale_worker")
        with Session(app.state.engine) as verify:
            row = verify.get(Upload, uid)
            assert row.lease_token == new_token and row.status == "receiving"
            assert row.failure_code is None


def test_concurrent_finalizers_deduplicate_in_database(materials):
    client, headers, admin, *_ = materials
    data = b"shared concurrent blob"
    uploads = [init(client, headers, data).json()["upload_id"] for _ in range(2)]
    for uid in uploads:
        assert (
            client.put(
                f"/api/v1/materials/uploads/{uid}/content", headers=headers, content=data
            ).status_code
            == 200
        )

    def complete(uid):
        return client.post(f"/api/v1/materials/uploads/{uid}/finalize", headers=headers)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(complete, uploads))
    assert [response.status_code for response in results] == [200, 200], [r.text for r in results]
    assert sorted(response.json()["deduplicated"] for response in results) == [False, True]
    with Session(app.state.engine) as db:
        blobs = db.scalars(select(Blob).where(Blob.workspace_id == admin.workspace_id)).all()
        assert len(blobs) == 1
