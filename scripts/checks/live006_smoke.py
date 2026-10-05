"""Real PG/material API/FFmpeg/controlled-worker smoke; ASR is synthetic, no broker."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import wave
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path("/Users/docfat/Desktop/个人/project/直播体系FDE")
RUNTIME = WORKSPACE / "runtime/live-006"
ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}


def environment():
    if ROOT != WORKSPACE / "app" or RUNTIME.resolve() != RUNTIME:
        raise RuntimeError("unregistered_checkout")
    path = RUNTIME / "private.env"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8192:
            raise RuntimeError("unsafe_private_environment")
        payload = source.read(8193)
    if len(payload) > 8192:
        raise RuntimeError("unsafe_private_environment")
    lines = payload.splitlines()
    values = dict(line.split("=", 1) for line in lines)
    if len(lines) != len(values) or set(values) != {
        "LIVE_RUNTIME",
        "PG_PASSWORD",
        "LIVE_DATABASE_URL",
        "LIVE_BROKER_URL",
        "LIVE_STORAGE_ROOT",
    }:
        raise RuntimeError("invalid_private_environment")
    password = values["PG_PASSWORD"]
    if not re.fullmatch("[0-9a-f]{48}", password) or values["LIVE_RUNTIME"] != str(RUNTIME):
        raise RuntimeError("invalid_private_environment")
    if (
        values["LIVE_DATABASE_URL"]
        != f"postgresql+psycopg://live006:{password}@127.0.0.1:15460/live006"
        or values["LIVE_STORAGE_ROOT"] != str(RUNTIME / "storage")
        or Path(values["LIVE_STORAGE_ROOT"]).resolve() != RUNTIME / "storage"
        or values["LIVE_BROKER_URL"] != "amqp://unconfigured:unconfigured@127.0.0.1:1//"
    ):
        raise RuntimeError("foreign_destination")
    result = {k: v for k, v in os.environ.items() if not k.startswith("LIVE_")}
    result.update({k: v for k, v in values.items() if k.startswith("LIVE_")})
    result.update(LIVE_ENVIRONMENT="development", LIVE_JOB_TEST_HANDLERS="false")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regression",
        action="store_true",
        help="Run real PG backend suite, explicitly excluding broker-only tests",
    )
    args = parser.parse_args()
    env = environment()
    for key in list(os.environ):
        if key.startswith("LIVE_"):
            del os.environ[key]
    os.environ.update({k: v for k, v in env.items() if k.startswith("LIVE_")})
    run_root = RUNTIME / "integration" / uuid4().hex
    run_root.mkdir(parents=True)

    def command(label, args):
        proc = subprocess.run(
            args,
            cwd=ROOT / "services/backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        (run_root / f"{label}.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode:
            raise RuntimeError(f"{label}_failed")
        return proc.stdout

    if args.regression:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url

        # Dedicated DB prevents fixture dispatchers consuming retained smoke outbox.
        # Connection options cannot isolate schemas: application statement_timeout
        # deliberately overrides libpq options. Never delete old evidence.
        database = "live006_suite_" + uuid4().hex
        engine = create_engine(env["LIVE_DATABASE_URL"], isolation_level="AUTOCOMMIT")
        with engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}" OWNER live006'))
        engine.dispose()
        isolated_url = make_url(env["LIVE_DATABASE_URL"]).set(database=database)
        from live_review.core.config import Settings
        from live_review.core.database import build_engine

        engine = build_engine(
            Settings(
                database_url=isolated_url.render_as_string(hide_password=False),
                broker_url=env["LIVE_BROKER_URL"],
            )
        )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == database
            assert connection.scalar(text("SELECT current_user")) == "live006"
        engine.dispose()
        env["LIVE_DATABASE_URL"] = isolated_url.render_as_string(hide_password=False)
        (run_root / "target.json").write_text(
            json.dumps(
                {"host": "127.0.0.1", "port": 15460, "database": database, "role": "live006"}
            )
        )
        env["LIVE_TEST_DATABASE_URL"] = env["LIVE_DATABASE_URL"]
        report = run_root / "pytest.xml"
        command(
            "regression",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "--ignore=tests/test_jobs_broker.py",
                f"--junitxml={report}",
                f"--basetemp={run_root / 'pytest-temp'}",
            ],
        )
        suites = list(ET.parse(report).iter("testsuite"))
        totals = {
            name: sum(int(s.get(name, "0")) for s in suites)
            for name in ("tests", "failures", "errors", "skipped")
        }
        if any(totals[name] for name in ("failures", "errors", "skipped")):
            raise RuntimeError("regression_not_clean")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "counts": totals,
                    "junit": str(report),
                    "excluded": "test_jobs_broker.py; no broker in LIVE-006",
                    "database": database,
                }
            )
        )
        return

    command("migration", [sys.executable, "-m", "alembic", "upgrade", "head"])
    source = run_root / "synthetic.mp4"
    command(
        "generate",
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000",
            "-t",
            "2.25",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            str(source),
        ],
    )
    config = run_root / "providers.yaml"
    config.write_text(
        (ROOT / "infra/providers.offline.example.yaml")
        .read_text()
        .replace("segment_seconds: 300", "segment_seconds: 1")
    )
    fixture = run_root / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "segments": {
                    str(i): {
                        "utterances": [
                            {"text": f"SYNTHETIC segment {i}", "start_ms": 0, "end_ms": 100}
                        ],
                        "coverage": "full",
                        "missing_words": False,
                        "no_speech": False,
                    }
                    for i in range(3)
                }
            }
        )
    )

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from live_review.core.config import get_settings
    from live_review.main import app
    from live_review.modules.identity.models import Admin, Workspace
    from live_review.modules.identity.security import hasher
    from live_review.modules.jobs.service import stages_for
    from live_review.workers.media_artifacts import controlled, read_json

    get_settings.cache_clear()
    username, password = "smoke-" + uuid4().hex, uuid4().hex
    with TestClient(app) as client:
        with Session(app.state.engine, expire_on_commit=False) as db:
            workspace = Workspace(name="LIVE-006 synthetic smoke")
            db.add(workspace)
            db.flush()
            admin = Admin(
                workspace_id=workspace.id,
                username=username,
                display_name="Synthetic smoke",
                password_hash=hasher.hash(password),
            )
            db.add(admin)
            db.commit()

        def request(method, path, expected=200, **kwargs):
            response = client.request(method, "/api/v1" + path, **kwargs)
            if response.status_code != expected:
                raise RuntimeError(f"api_{response.status_code}_{path}")
            return response.json()

        login = request(
            "POST", "/auth/login", headers=ORIGIN, json={"username": username, "password": password}
        )
        headers = ORIGIN | {"X-CSRF-Token": login["csrf_token"]}
        streamer = request(
            "POST",
            "/streamers",
            201,
            headers=headers,
            json={"name": "Synthetic media", "platform": "other"},
        )
        live = request(
            "POST",
            "/sessions",
            201,
            headers=headers,
            json={
                "streamer_id": streamer["id"],
                "title": "LIVE-006 smoke",
                "platform": "other",
                "session_local_date": date.today().isoformat(),
            },
        )
        data = source.read_bytes()
        upload = request(
            "POST",
            "/materials/uploads",
            201,
            headers=headers | {"Idempotency-Key": uuid4().hex},
            json={
                "filename": "synthetic.mp4",
                "byte_size": len(data),
                "media_type": "video/mp4",
                "purpose": "session_media",
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        uid = upload["upload_id"]
        request("PUT", f"/materials/uploads/{uid}/content", headers=headers, content=data)
        material = request("POST", f"/materials/uploads/{uid}/finalize", headers=headers)
        material_id = material.get("material_id") or material["id"]
        request(
            "POST",
            f"/sessions/{live['id']}/materials",
            201,
            headers=headers,
            json={"material_id": material_id, "role": "primary"},
        )
        base = [sys.executable, "-m", "live_review.workers.media_operator"]
        result = command(
            "submit",
            base
            + [
                "submit",
                "--workspace-id",
                str(workspace.id),
                "--admin-id",
                str(admin.id),
                "--material-id",
                str(material_id),
                "--config",
                str(config),
                "--fixture",
                str(fixture),
            ],
        )
        job_id = json.loads(result.strip().splitlines()[-1])["job_id"]
        command(
            "run-local",
            base
            + [
                "run-local",
                "--workspace-id",
                str(workspace.id),
                "--admin-id",
                str(admin.id),
                "--job-id",
                job_id,
            ],
        )
        job = request("GET", f"/jobs/{job_id}")
        assert job["status"] == "succeeded", job
        with Session(app.state.engine) as db:
            stages = stages_for(db, UUID(job_id))
            references = {stage.name: stage.artifact for stage in stages}
        storage = Path(env["LIVE_STORAGE_ROOT"])
        extraction = read_json(storage, references["extract"])
        transcript = read_json(storage, references["asr"])
        assert extraction["source_sha256"] == hashlib.sha256(data).hexdigest()
        assert transcript["complete"] and transcript["synthetic"]
        assert len(extraction["segments"]) == 3
        artifact_root = controlled(storage, references["extract"]["artifact_root"])
        wav = controlled(artifact_root, extraction["audio"]["path"])
        with wave.open(str(wav), "rb") as audio:
            assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (
                16000,
                1,
                2,
            )
            assert audio.getnframes() == extraction["audio_samples"]
        assert [u["start_ms"] for u in transcript["utterances"]] == [0, 1000, 2000]
        report = {
            "job": job,
            "artifacts": references,
            "wav": str(wav),
            "transcript": str(controlled(storage, references["asr"]["artifact_ref"])),
            "material_id": material_id,
            "session_id": live["id"],
            "workspace_id": str(workspace.id),
            "admin_id": str(admin.id),
            "source": str(source),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "provider_yaml": str(config),
            "fixture": str(fixture),
            "synthetic_asr": True,
            "external_model_calls": 0,
            "transport": "005 runner local; broker not exercised",
        }
        (run_root / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps({"status": "passed", "result": str(run_root / "result.json")}))


if __name__ == "__main__":
    main()
