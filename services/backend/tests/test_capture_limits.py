from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from capture_fixture import av_file as av_file
from capture_fixture import capture_env as capture_env
from capture_fixture import closed_fixture, start_run
from capture_fixture import materials as materials
from sqlalchemy.orm import Session

from live_review.integrations.capture import limits
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import CapturePolicy
from live_review.integrations.storage.local import LocalStorage, hash_file
from live_review.main import app
from live_review.modules.capture.schemas import StartInput
from live_review.modules.jobs.models import Job
from live_review.workers.job_runner import run_job


def test_defaults_capacity_and_ceilings(monkeypatch):
    policy = CapturePolicy()
    selected = limits.select_limits(policy)
    assert (selected.max_seconds, selected.max_bytes) == (7200, 8 * limits.GIB)
    monkeypatch.setattr(limits, "disk", lambda path: (1, 34 * limits.GIB))
    health = limits.health_limits(
        policy, SimpleNamespace(storage_root="/s", upload_max_bytes=512 * 1024**2)
    )
    assert health["duration_presets_seconds"] == [1800, 3600, 7200, 14400]
    assert health["available_max_bytes"] < 16 * limits.GIB
    limits.require_capacity("/c", "/s", 2 * limits.GIB, 8 * limits.GIB, before_start=True)
    with pytest.raises(CaptureError, match="disk_full"):
        limits.require_capacity("/c", "/s", 2 * limits.GIB, 16 * limits.GIB, before_start=True)
    monkeypatch.setattr(
        limits, "disk", lambda path: (1, 20 * limits.GIB) if path == "/c" else (2, 10 * limits.GIB)
    )
    with pytest.raises(CaptureError, match="disk_full"):
        limits.require_capacity("/c", "/s", 2 * limits.GIB, 8 * limits.GIB, before_start=True)
    with pytest.raises(CaptureError, match="disk_full"):
        limits.require_capacity("/c", "/s", 2 * limits.GIB, 5 * limits.GIB)


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration_seconds", True),
        ("duration_seconds", 14401),
        ("max_bytes", 16 * limits.GIB + 1),
        ("max_bytes", "10000000"),
    ],
)
def test_strict_inputs(field, value):
    with pytest.raises(ValueError):
        StartInput(session_id=uuid4(), platform="wechat", source_ref="phone_cast", **{field: value})


def test_limits_snapshot_never_changes_base_policy():
    base = CapturePolicy()
    small = limits.select_limits(base, 1800, limits.GIB).model_dump()
    effective = limits.effective_policy(base, {"recording_limits": small})
    assert effective.max_seconds == 1800 and base.max_seconds == 14400
    for invalid in (
        small | {"max_seconds": 14401},
        small | {"min_free_bytes": 1},
        small | {"max_bytes": True},
    ):
        with pytest.raises(CaptureError, match="invalid_recording_limits"):
            limits.effective_policy(base, {"recording_limits": invalid})


def test_streaming_hash_copy_cancellation(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"x" * (3 * 1024**2))
    calls = []
    assert len(hash_file(source, lambda: calls.append(1))) == 64
    assert len(calls) == 4

    def cancel():
        raise RuntimeError("lease_lost")

    with pytest.raises(RuntimeError, match="lease_lost"):
        hash_file(source, cancel)
    storage = LocalStorage(tmp_path / "storage")
    with pytest.raises(RuntimeError, match="lease_lost"):
        storage.promote_copy(source, uuid4(), tick=cancel)
    assert source.exists()


def test_capture_scoped_import_and_manual_limit(capture_env, av_file, monkeypatch):
    fixture, settings, root = capture_env
    client, headers, _, _, _ = fixture
    small = settings.model_copy(update={"upload_max_bytes": 1})
    monkeypatch.setattr(app.state, "settings", small)
    run, data = start_run(fixture)
    assert run["recording_limits"]["max_seconds"] == 30
    assert run["recorded_bytes"] is None
    closed_fixture(root, run, av_file)
    run_job(app.state.engine, small, run["job_id"], 1)
    result = client.get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()
    assert result["state"] == "imported", result
    assert result["recorded_bytes"] == av_file.stat().st_size
    assert small.upload_max_bytes == 1
    manual = client.post(
        "/api/v1/materials/uploads",
        headers=headers | {"Idempotency-Key": "manual-limit"},
        json={
            "filename": "test.mp4",
            "byte_size": av_file.stat().st_size,
            "media_type": "video/mp4",
            "purpose": "session_media",
        },
    )
    assert manual.status_code == 413, manual.text


def test_invalid_snapshot_never_imports(capture_env, av_file):
    fixture, settings, root = capture_env
    run, _ = start_run(fixture)
    closed_fixture(root, run, av_file)
    with Session(app.state.engine) as db:
        job = db.get(Job, UUID(run["job_id"]))
        job.input_data = job.input_data | {
            "recording_limits": {
                "max_seconds": 14400,
                "max_bytes": 16 * limits.GIB,
                "min_free_bytes": 1048576,
            }
        }
        db.commit()
    run_job(app.state.engine, settings, run["job_id"], 1)
    result = fixture[0].get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()
    assert result["material_id"] is None


def test_upload_pulse_renews_lease_and_propagates_cancel(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from live_review.modules.materials import transfer

    instant = datetime.now(UTC)
    row = SimpleNamespace(lease_until=instant)
    calls = []
    monkeypatch.setattr(transfer, "locked_lease", lambda *args: row)
    monkeypatch.setattr(transfer, "now", lambda: instant)
    clock = iter([100.0, 100.5, 101.1])
    monkeypatch.setattr(transfer.time, "monotonic", lambda: next(clock))
    db = SimpleNamespace(commit=lambda: calls.append("commit"))
    pulse = transfer.transfer_pulse(
        db, None, None, None, SimpleNamespace(upload_lease_seconds=30), lambda: calls.append("tick")
    )
    pulse()
    pulse()
    pulse()
    assert calls == ["tick", "commit", "tick", "tick", "commit"]
    assert row.lease_until == instant + timedelta(seconds=30)


def test_probe_checks_cancellation(tmp_path):
    from live_review.integrations.capture.recording import inspect_media
    from live_review.modules.jobs.execution import Canceled

    def cancel():
        raise Canceled

    with pytest.raises(Canceled):
        inspect_media(tmp_path / "unused", "ffprobe", cancel)


def test_four_hour_budget_uses_fragmented_mp4_without_waiting(tmp_path, av_file, monkeypatch):
    import subprocess

    from test_capture_recording import http_source, permit_fixture

    from live_review.integrations.capture import recording, relay
    from live_review.integrations.capture.contracts import Source

    original = subprocess.Popen
    commands = []

    def observe(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(recording.subprocess, "Popen", observe)
    monkeypatch.setattr(relay, "destination", permit_fixture)
    output = tmp_path / "long-budget"
    output.mkdir()
    with http_source(av_file) as url:
        manifest = recording.record(
            Source(True, url),
            output,
            CapturePolicy(max_seconds=14400, max_bytes=8 * limits.GIB, min_free_bytes=1048576),
            lambda: None,
            lambda _: None,
            "wechat",
            uuid4(),
            "phone_cast",
        )
    command = next(command for command in commands if command[0] == "ffmpeg")
    assert command[command.index("-t") + 1] == "14400"
    assert command[command.index("-fs") + 1] == str(8 * limits.GIB)
    assert "frag_keyframe" in command[command.index("-movflags") + 1]
    assert manifest["closed"] and manifest["duration_ms"] < 3000


def test_real_65_seconds_capture_closes_and_imports(capture_env, tmp_path, monkeypatch):
    import subprocess

    from test_capture_recording import http_source, permit_fixture

    from live_review.integrations.capture import recording, relay
    from live_review.integrations.capture.contracts import Source
    from live_review.integrations.capture.policy import load_policy

    fixture, settings, root = capture_env
    config = settings.model_config_dir / "capture.local.yaml"
    config.write_text(config.read_text().replace("max_seconds: 30", "max_seconds: 14400"))
    source = tmp_path / "synthetic-65-seconds.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=32x32:rate=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000",
            "-t",
            "65",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    run, _ = start_run(fixture, platform="wechat")
    path = root / run["capture_run_id"]
    path.mkdir(exist_ok=True)
    policy = load_policy(settings)
    effective = limits.effective_policy(policy, {"recording_limits": run["recording_limits"]})
    monkeypatch.setattr(relay, "destination", permit_fixture)
    with http_source(source) as url:
        manifest = recording.record(
            Source(True, url),
            path,
            effective,
            lambda: None,
            lambda _: None,
            "wechat",
            UUID(run["capture_run_id"]),
            "phone_cast",
            storage_root=settings.storage_root,
        )
    assert manifest["closed"] and manifest["duration_ms"] >= 65000
    assert manifest["end_reason"] == "source_eof_unconfirmed"
    run_job(app.state.engine, settings, run["job_id"], 1)
    result = fixture[0].get(f"/api/v1/capture/runs/{run['capture_run_id']}").json()
    assert result["state"] == "imported", result
    assert result["elapsed_seconds"] >= 65
    assert result["material_id"] and result["transcription_status"] == "not_requested"
    media = fixture[0].get(f"/api/v1/materials/{result['material_id']}/content")
    assert media.status_code == 200 and len(media.content) == manifest["size_bytes"]
