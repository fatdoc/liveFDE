"""Real PG identity-to-session contract tests, with isolated synthetic tenants."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from live_review.core.auth import COOKIE_NAME
from live_review.core.config import get_settings
from live_review.main import app
from live_review.modules.identity.models import Admin, AuthSession, Workspace
from live_review.modules.identity.security import hasher
from live_review.modules.sessions.models import LiveSession
from live_review.modules.streamers.models import Streamer

ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}
PASSWORD = "synthetic-session-fixture-password"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def context(monkeypatch):
    url = os.getenv("LIVE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit isolated real PG required")
    monkeypatch.setenv("LIVE_DATABASE_URL", url)
    get_settings.cache_clear()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)
    accounts = []
    with TestClient(app, client=(uuid4().hex, 50000)) as client:
        with Session(app.state.engine) as db:
            for _ in range(2):
                workspace = Workspace(name="Session fixture")
                db.add(workspace)
                db.flush()
                admin = Admin(
                    workspace_id=workspace.id,
                    username=uuid4().hex,
                    display_name="Fixture",
                    password_hash=hasher.hash(PASSWORD),
                )
                db.add(admin)
                db.flush()
                accounts.append((workspace.id, admin.id, admin.username))
            db.commit()
        response = client.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"username": accounts[0][2], "password": PASSWORD},
        )
        assert response.status_code == 200
        headers = ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}
        yield client, headers, accounts
        with Session(app.state.engine) as db:
            for workspace_id, admin_id, _ in accounts:
                db.execute(delete(LiveSession).where(LiveSession.workspace_id == workspace_id))
                db.execute(delete(Streamer).where(Streamer.workspace_id == workspace_id))
                db.execute(delete(AuthSession).where(AuthSession.admin_id == admin_id))
                db.execute(delete(Admin).where(Admin.id == admin_id))
                db.execute(delete(Workspace).where(Workspace.id == workspace_id))
            db.commit()
    get_settings.cache_clear()


def create(client, headers, **changes):
    streamer = client.post(
        "/api/v1/streamers", headers=headers, json={"name": "主播甲", "platform": "douyin"}
    )
    assert streamer.status_code == 201, streamer.text
    payload = {
        "streamer_id": streamer.json()["id"],
        "title": "开场100%_测试",
        "platform": "douyin",
        "session_local_date": "2026-10-05",
    } | changes
    return client.post("/api/v1/sessions", headers=headers, json=payload)


def test_create_filter_empty_and_restart(context):
    client, headers, accounts = context
    assert client.get("/api/v1/sessions").json()["items"] == []
    response = create(client, headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["started_at"] is data["duration_ms"] is None
    assert data["time_precision"] == "date" and data["processing_status"] == "pending"
    assert data["time_source"] == "user_entered"
    filtered = client.get(
        "/api/v1/sessions",
        params={"q": "100%_", "from": "2026-10-05", "to": "2026-10-06", "platform": "douyin"},
    )
    assert filtered.json()["total"] == 1
    assert client.get("/api/v1/sessions?from=2026-10-06").json()["total"] == 0
    assert client.get("/api/v1/sessions?limit=1&offset=1").json()["items"] == []
    assert client.get("/api/v1/sessions?limit=101").status_code == 422
    assert client.get("/api/v1/sessions?from=2026-10-05&to=2026-10-05").status_code == 422
    cookie = client.cookies.get(COOKIE_NAME)
    with TestClient(app) as restarted:
        result = restarted.get(
            f"/api/v1/sessions/{data['id']}", headers={"Cookie": f"{COOKIE_NAME}={cookie}"}
        )
        assert result.status_code == 200
        assert result.json()["title"] == data["title"]


def test_invalid_date_precision_and_csrf(context):
    client, headers, _ = context
    for changes in (
        {"started_at": "2026-10-05T00:00:00+08:00"},
        {"time_precision": "minute"},
        {"started_at": "2026-10-04T23:00:00+08:00", "time_precision": "second"},
        {"started_at": "2026-10-05T09:00:01+08:00", "time_precision": "minute"},
        {"started_at": "2026-10-05T09:00:00", "time_precision": "second"},
        {"workspace_id": str(uuid4())},
        {"duration_ms": 5000},
    ):
        assert create(client, headers, **changes).status_code == 422
    valid = create(client, headers, started_at="2026-10-05T09:00:00+08:00", time_precision="minute")
    assert valid.status_code == 201
    session_id = valid.json()["id"]
    assert (
        client.patch(
            f"/api/v1/sessions/{session_id}",
            headers=ORIGIN,
            json={"expected_revision": 1, "title": "Changed"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/sessions/{session_id}",
            headers=headers,
            json={"expected_revision": 1, "session_local_date": "2026-10-06"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/sessions/{session_id}",
            headers=headers,
            json={"expected_revision": 1, "title": None},
        ).status_code
        == 422
    )


def test_concurrent_revision_and_workspace_boundary(context):
    client, headers, accounts = context
    data = create(client, headers).json()
    url = "/api/v1/sessions/" + data["id"]

    def edit(number):
        return client.patch(
            url, headers=headers, json={"expected_revision": 1, "title": f"Revision {number}"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(edit, [1, 2])) == [200, 409]
    assert client.get(url).json()["revision"] == 2
    with TestClient(app, client=(uuid4().hex, 50000)) as other:
        assert other.get(url).status_code == 401
        result = other.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"username": accounts[1][2], "password": PASSWORD},
        )
        other_headers = ORIGIN | {"X-CSRF-Token": result.json()["csrf_token"]}
        assert other.get(url).status_code == 404
        assert other.get("/api/v1/sessions").json()["total"] == 0
        assert (
            other.patch(
                url, headers=other_headers, json={"expected_revision": 2, "title": "Hijack"}
            ).status_code
            == 404
        )
        assert (
            other.post(
                "/api/v1/sessions",
                headers=other_headers,
                json={
                    "streamer_id": data["streamer_id"],
                    "title": "Cross",
                    "platform": "douyin",
                    "session_local_date": "2026-10-05",
                },
            ).status_code
            == 404
        )
    with Session(app.state.engine) as db:
        row = db.scalar(select(LiveSession).where(LiveSession.id == data["id"]))
        row.workspace_id = accounts[1][0]
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
