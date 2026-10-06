"""Small synthetic AV fixtures and real isolated PG; no platform/network model claims."""

import json
import subprocess

import pytest
from materials_fixture import materials as materials
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from live_review.main import app
from live_review.modules.capture.models import CaptureRun
from live_review.modules.jobs.models import CallIntent, Job, JobStage, Outbox, RetryKey


@pytest.fixture
def capture_env(materials, tmp_path, monkeypatch):
    root = tmp_path / "captures"
    root.mkdir()
    config = tmp_path / "config"
    config.mkdir()
    (config / "capture.local.yaml").write_text(
        f"enabled: true\nroot: {root}\nmin_free_bytes: 1048576\nmax_seconds: 30\n"
        "max_bytes: 4194304\ndefault_max_bytes: 2097152\n"
    )
    settings = app.state.settings.model_copy(update={"model_config_dir": config})
    monkeypatch.setattr(app.state, "settings", settings)
    yield materials, settings, root
    admin = materials[2]
    with Session(app.state.engine) as db:
        ids = select(Job.id).where(Job.workspace_id == admin.workspace_id)
        db.execute(delete(CaptureRun).where(CaptureRun.workspace_id == admin.workspace_id))
        for model in (CallIntent, RetryKey, Outbox, JobStage):
            db.execute(delete(model).where(model.job_id.in_(ids)))
        db.execute(delete(Job).where(Job.workspace_id == admin.workspace_id))
        db.commit()


@pytest.fixture
def av_file(tmp_path):
    target = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x90:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(target),
        ],
        check=True,
        timeout=20,
    )
    return target


def start_run(fixture, platform="douyin", key="capture-test"):
    client, headers, _, sessions, _ = fixture
    data = {
        "session_id": str(sessions[0].id),
        "platform": platform,
        "source_ref": "phone_cast" if platform == "wechat" else "https://live.douyin.com/12345",
    }
    result = client.post(
        "/api/v1/capture/runs", json=data, headers=headers | {"Idempotency-Key": key}
    )
    assert result.status_code == 202, result.text
    return result.json(), data


def closed_fixture(root, run, source, complete=True):
    import hashlib
    import shutil
    from datetime import UTC, datetime

    path = root / run["capture_run_id"]
    path.mkdir(exist_ok=True)
    shutil.copyfile(source, path / "recording.mp4")
    content = source.read_bytes()
    manifest = {
        "schema_version": 1,
        "platform": run["platform"],
        "capture_run_id": run["capture_run_id"],
        "source_ref": run["source_ref"],
        "started_at": datetime.now(UTC).isoformat(),
        "ended_at": datetime.now(UTC).isoformat(),
        "duration_ms": 2000,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "file": "recording.mp4",
        "media_types": ["audio", "video"],
        "complete": complete,
        "closed": True,
        "end_reason": "user_stop",
        "segment_index": 0,
    }
    (path / "manifest.json").write_text(json.dumps(manifest))
    return manifest
