import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from live_review.core.config import get_settings
from live_review.main import app
from live_review.modules.identity.models import Admin, AuthSession, Workspace
from live_review.modules.identity.security import hasher
from live_review.modules.jobs.models import CallIntent, Job, JobStage, Outbox, RetryKey
from live_review.modules.jobs.router import router
from live_review.modules.jobs.service import create_job

ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def jobs(monkeypatch):
    if not os.environ.get("LIVE_TEST_DATABASE_URL"):
        pytest.skip("Real isolated PG required")
    monkeypatch.setenv("LIVE_DATABASE_URL", os.environ["LIVE_TEST_DATABASE_URL"])
    monkeypatch.setenv("LIVE_JOB_TEST_HANDLERS", "true")
    monkeypatch.setenv("LIVE_JOB_LEASE_SECONDS", "3")
    get_settings.cache_clear()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )
    if "/api/v1/jobs/{job_id}" not in app.openapi()["paths"]:
        app.include_router(router)
        app.openapi_schema = None
    with TestClient(app, client=(f"fd00::{uuid4().int % 65535:x}", 50000)) as client:
        with Session(app.state.engine, expire_on_commit=False) as db:
            workspace = Workspace(name="Synthetic jobs tenant")
            db.add(workspace)
            db.flush()
            admin = Admin(
                workspace_id=workspace.id,
                username=uuid4().hex,
                display_name="Fixture",
                password_hash=hasher.hash("synthetic-job-password"),
            )
            db.add(admin)
            db.commit()
        response = client.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"username": admin.username, "password": "synthetic-job-password"},
        )
        assert response.status_code == 200
        headers = ORIGIN | {"X-CSRF-Token": response.json()["csrf_token"]}

        def make(handlers=None, data=None):
            with Session(app.state.engine, expire_on_commit=False) as db:
                job = create_job(
                    db,
                    admin.workspace_id,
                    admin.id,
                    [
                        {"name": f"stage{i}", "handler": handler}
                        for i, handler in enumerate(handlers or ["fixture.echo"])
                    ],
                    data or {"value": "synthetic"},
                )
                db.commit()
                return job.id

        yield client, headers, admin, make, app.state.engine, app.state.settings
        with Session(app.state.engine) as db:
            ids = select(Job.id).where(Job.workspace_id == workspace.id)
            for model in [CallIntent, RetryKey, Outbox, JobStage]:
                db.execute(delete(model).where(model.job_id.in_(ids)))
            db.execute(delete(Job).where(Job.workspace_id == workspace.id))
            db.execute(delete(AuthSession).where(AuthSession.admin_id == admin.id))
            db.delete(db.get(Admin, admin.id))
            db.delete(db.get(Workspace, workspace.id))
            db.commit()
    get_settings.cache_clear()
