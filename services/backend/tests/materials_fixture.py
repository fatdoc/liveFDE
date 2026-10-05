"""Real PG + actual synthetic formats; no provider, no binary fixtures in Git."""

import hashlib
import io
import os
import subprocess
import sys
import wave
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.main import app
from live_review.modules.identity.models import Admin, Workspace
from live_review.modules.identity.security import hasher
from live_review.modules.materials.router import router
from live_review.modules.sessions.models import LiveSession
from live_review.modules.streamers.models import Streamer

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}
PASSWORD = "synthetic-material-password"


@pytest.fixture
def materials(monkeypatch):
    url = os.environ.get("LIVE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Real isolated LIVE_TEST_DATABASE_URL required")
    monkeypatch.setenv("LIVE_DATABASE_URL", url)
    get_settings.cache_clear()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    # Explicit composition uses real router/dependencies; ARC wires production main.
    if not any(getattr(route, "path", "") == "/api/v1/materials/uploads" for route in app.routes):
        app.include_router(router, prefix="/api/v1")
    with TestClient(
        app, raise_server_exceptions=False, client=(f"fd00::{uuid4().int % 65535:x}", 50000)
    ) as client:
        seed = uuid4().hex
        with Session(app.state.engine, expire_on_commit=False) as db:
            workspace = Workspace(name="Synthetic material tenant")
            foreign = Workspace(name="Other synthetic tenant")
            db.add_all([workspace, foreign])
            db.flush()
            admin = Admin(
                workspace_id=workspace.id,
                username=seed,
                display_name="Fixture",
                password_hash=hasher.hash(PASSWORD),
            )
            stranger = Admin(
                workspace_id=foreign.id,
                username=seed + "other",
                display_name="Other",
                password_hash=hasher.hash(PASSWORD),
            )
            db.add_all([admin, stranger])
            db.flush()
            streamer = Streamer(workspace_id=workspace.id, name="Fixture", platform="manual")
            db.add(streamer)
            db.flush()
            sessions = [
                LiveSession(
                    workspace_id=workspace.id,
                    streamer_id=streamer.id,
                    title=f"Synthetic {i}",
                    platform="manual",
                    session_local_date=date.today(),
                    started_at=None,
                    time_precision="date",
                    time_source="user_entered",
                    timezone="Asia/Shanghai",
                )
                for i in range(2)
            ]
            db.add_all(sessions)
            db.commit()
        response = client.post(
            "/api/v1/auth/login", headers=ORIGIN, json={"username": seed, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        headers = ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}
        yield client, headers, admin, sessions, stranger
    get_settings.cache_clear()


def init(client, headers, data, media_type="text/plain", purpose="transcript", key=None, **extra):
    body = {
        "filename": "../../display-only.txt",
        "byte_size": len(data),
        "media_type": media_type,
        "purpose": purpose,
        "sha256": hashlib.sha256(data).hexdigest(),
    } | extra
    return client.post(
        "/api/v1/materials/uploads",
        headers=headers | {"Idempotency-Key": key or str(uuid4())},
        json=body,
    )


def upload(client, headers, data, media_type="text/plain", purpose="transcript"):
    response = init(client, headers, data, media_type, purpose)
    assert response.status_code == 201, response.text
    uid = response.json()["upload_id"]
    sent = client.put(f"/api/v1/materials/uploads/{uid}/content", headers=headers, content=data)
    assert sent.status_code == 200, sent.text
    done = client.post(f"/api/v1/materials/uploads/{uid}/finalize", headers=headers)
    assert done.status_code == 200, done.text
    return uid, done.json()


def wav_bytes():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\0\0" * 1600)
    return stream.getvalue()
