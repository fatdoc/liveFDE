"""Opt-in real PostgreSQL tests; migrations, never metadata.create_all."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from live_review.core.auth import COOKIE_NAME, token_hash
from live_review.core.config import get_settings
from live_review.main import app
from live_review.modules.identity.models import Admin, AuthSession, LoginThrottle, Workspace
from live_review.modules.identity.security import hasher, reserve_attempt

PASSWORD = "synthetic-fixture-password"
ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def identity(monkeypatch):
    url = os.environ.get("LIVE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("LIVE_TEST_DATABASE_URL required for real PostgreSQL integration")
    monkeypatch.setenv("LIVE_DATABASE_URL", url)
    monkeypatch.setenv("LIVE_BROKER_URL", "amqp://unused:unused@127.0.0.1:1//")
    get_settings.cache_clear()
    for _ in range(2):
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    with TestClient(app) as client:
        username = "fixture-" + uuid4().hex
        with Session(app.state.engine) as db:
            workspace = Workspace(name="Synthetic tenant")
            db.add(workspace)
            db.flush()
            admin = Admin(
                workspace_id=workspace.id,
                username=username,
                display_name="Synthetic",
                password_hash=hasher.hash(PASSWORD),
            )
            db.add(admin)
            db.commit()
            admin_id, workspace_id = admin.id, workspace.id
        yield client, username, admin_id, workspace_id
        with Session(app.state.engine) as db:
            db.query(AuthSession).filter(AuthSession.admin_id == admin_id).delete()
            db.query(Admin).filter(Admin.id == admin_id).delete()
            db.query(Workspace).filter(Workspace.id == workspace_id).delete()
            db.query(LoginThrottle).delete()
            db.commit()
    get_settings.cache_clear()


def login(client, username, **extra):
    return client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD, **extra},
    )


def test_login_rotation_logout_and_scope(identity):
    client, username, _, workspace = identity
    first = login(client, username)
    assert first.status_code == 200
    assert first.json()["user"]["workspace_id"] == str(workspace)
    assert "HttpOnly" in first.headers["set-cookie"]
    assert "SameSite=lax" in first.headers["set-cookie"]
    old = client.cookies.get(COOKIE_NAME)
    second = login(client, username)
    assert second.status_code == 200
    assert client.cookies.get(COOKIE_NAME) != old
    assert (
        client.get("/api/v1/auth/me", headers={"Cookie": f"{COOKIE_NAME}={old}"}).status_code == 401
    )
    me = client.get("/api/v1/auth/me")
    assert me.json()["user"]["workspace_id"] == str(workspace)
    assert me.headers["cache-control"] == "private,no-store"
    assert client.post("/api/v1/auth/logout", headers=ORIGIN).status_code == 403
    current = client.cookies.get(COOKIE_NAME)
    csrf = {**ORIGIN, "X-CSRF-Token": second.json()["csrf_token"]}
    assert client.post("/api/v1/auth/logout", headers=csrf).status_code == 204
    assert (
        client.get("/api/v1/auth/me", headers={"Cookie": f"{COOKIE_NAME}={current}"}).status_code
        == 401
    )


def test_origin_validation_and_safe_errors(identity):
    client, username, _, _ = identity
    for headers in (
        {},
        {"Origin": "https://evil.invalid"},
        {**ORIGIN, "Sec-Fetch-Site": "cross-site"},
        {"Origin": "https://evil.invalid", "Host": "evil.invalid"},
    ):
        assert (
            client.post(
                "/api/v1/auth/login",
                headers=headers,
                json={"username": username, "password": PASSWORD},
            ).status_code
            == 403
        )
    assert login(client, username, workspace_id=str(uuid4())).status_code == 422
    response = client.post(
        "/api/v1/auth/login", headers=ORIGIN, json={"username": "missing", "password": "wrong"}
    )
    wrong = client.post(
        "/api/v1/auth/login", headers=ORIGIN, json={"username": username, "password": "wrong"}
    )
    assert response.status_code == wrong.status_code == 401
    assert response.json()["code"] == wrong.json()["code"]
    assert "wrong" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_expiration_and_disable(identity):
    client, username, admin_id, _ = identity
    assert login(client, username).status_code == 200
    with Session(app.state.engine) as db:
        auth = db.get(AuthSession, token_hash(client.cookies.get(COOKIE_NAME)))
        auth.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client, username).status_code == 200
    with Session(app.state.engine) as db:
        db.get(Admin, admin_id).active = False
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client, username).status_code == 401


def test_persistent_concurrent_throttle(identity):
    from live_review.core.errors import ApiError

    client, username, _, _ = identity
    settings = app.state.settings.model_copy(update={"login_limit": 3})

    def attempt(_):
        with Session(app.state.engine) as db:
            try:
                reserve_attempt(db, settings, username, "synthetic-throttle")
                return 200
            except ApiError as exc:
                return exc.status

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(attempt, range(6)))
    assert results.count(200) == results.count(429) == 3
    with Session(app.state.engine) as db:
        assert (
            db.scalar(
                select(LoginThrottle).where(LoginThrottle.bucket == token_hash("user:" + username))
            ).attempts
            == 3
        )


def test_bootstrap_cli(identity):
    client, _, _, workspace_id = identity
    username = "cli-" + uuid4().hex
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "live_review.modules.identity.cli",
            "--username",
            username,
            "--display-name",
            "CLI fixture",
            "--workspace-id",
            str(workspace_id),
            "--password-stdin",
        ],
        input=PASSWORD + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert PASSWORD not in result.stdout + result.stderr
    with Session(app.state.engine) as db:
        admin = db.scalar(select(Admin).where(Admin.username == username))
        assert admin.password_hash.startswith("$argon2id$")
        db.delete(admin)
        db.commit()
