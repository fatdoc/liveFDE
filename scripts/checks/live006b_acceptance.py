"""LIVE-006B isolated PG registry/legacy CLI acceptance; no external model calls."""

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
from pathlib import Path
from uuid import UUID, uuid4

WORKSPACE = Path("/Users/docfat/Desktop/个人/project/直播体系FDE")
ROOT = Path(__file__).resolve().parents[2]
RUNTIME = WORKSPACE / "runtime/live-006b"


def environment():
    if ROOT != WORKSPACE / "app" or RUNTIME.resolve() != RUNTIME:
        raise RuntimeError("unregistered_acceptance_checkout")
    path = RUNTIME / "private.env"
    if path.resolve() != path:
        raise RuntimeError("unsafe_private_environment")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r") as source:
        mode = os.fstat(source.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077 or mode.st_size > 8192:
            raise RuntimeError("unsafe_private_environment")
        raw = source.read(8193)
    lines = raw.splitlines()
    values = dict(line.split("=", 1) for line in lines)
    if (
        len(raw) > 8192
        or len(lines) != len(values)
        or set(values)
        != {
            "LIVE_RUNTIME",
            "PG_PASSWORD",
            "LIVE_DATABASE_URL",
            "LIVE_BROKER_URL",
            "LIVE_STORAGE_ROOT",
        }
    ):
        raise RuntimeError("invalid_private_environment")
    password = values["PG_PASSWORD"]
    if (
        not re.fullmatch("[a-f0-9]{48}", password)
        or values["LIVE_DATABASE_URL"]
        != f"postgresql+psycopg://live006b:{password}@127.0.0.1:15470/live006b"
        or values["LIVE_RUNTIME"] != str(RUNTIME)
        or values["LIVE_STORAGE_ROOT"] != str(RUNTIME / "storage")
        or (RUNTIME / "storage").resolve() != RUNTIME / "storage"
        or values["LIVE_BROKER_URL"] != "amqp://unconfigured:unconfigured@127.0.0.1:1//"
    ):
        raise RuntimeError("foreign_acceptance_destination")
    result = {k: v for k, v in os.environ.items() if not k.startswith("LIVE_")}
    result.update({k: v for k, v in values.items() if k.startswith("LIVE_")})
    result.update(LIVE_ENVIRONMENT="development", LIVE_JOB_TEST_HANDLERS="false")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="store_true")
    args = parser.parse_args()
    env = environment()
    run = RUNTIME / "integration" / uuid4().hex
    run.mkdir(parents=True)

    def command(label, arguments):
        result = subprocess.run(
            arguments,
            cwd=ROOT / "services/backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        (run / f"{label}.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(label + "_failed")
        return result.stdout

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from live_review.core.config import Settings
    from live_review.core.database import build_engine

    database = "live006b_suite_" + uuid4().hex
    control = create_engine(env["LIVE_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with control.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}" OWNER live006b'))
    control.dispose()
    env["LIVE_DATABASE_URL"] = (
        make_url(env["LIVE_DATABASE_URL"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )
    env["LIVE_TEST_DATABASE_URL"] = env["LIVE_DATABASE_URL"]
    settings = Settings(
        environment="development",
        job_test_handlers=False,
        database_url=env["LIVE_DATABASE_URL"],
        broker_url=env["LIVE_BROKER_URL"],
        storage_root=Path(env["LIVE_STORAGE_ROOT"]),
    )
    engine = build_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == database
        assert connection.scalar(text("SELECT current_user")) == "live006b"
    (run / "target.json").write_text(
        json.dumps({"database": database, "role": "live006b", "port": 15470})
    )
    if args.suite:
        report = run / "pytest.xml"
        command(
            "suite",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "--ignore=tests/test_jobs_broker.py",
                f"--junitxml={report}",
                f"--basetemp={run / 'pytest-temp'}",
            ],
        )
        suites = list(ET.parse(report).iter("testsuite"))
        counts = {
            key: sum(int(s.get(key, "0")) for s in suites)
            for key in ("tests", "errors", "failures", "skipped")
        }
        assert all(counts[k] == 0 for k in ("errors", "failures", "skipped"))
        print(json.dumps({"counts": counts, "report": str(report), "database": database}))
        engine.dispose()
        return
    command("migrate", [sys.executable, "-m", "alembic", "upgrade", "head"])
    smoke(run, env, engine, command)
    engine.dispose()


def smoke(run, env, engine, command):
    import yaml
    from sqlalchemy.orm import Session

    from live_review.modules.identity.models import Admin, Workspace
    from live_review.modules.identity.security import hasher
    from live_review.modules.jobs.models import Job
    from live_review.modules.jobs.service import now, stages_for
    from live_review.modules.materials.models import Blob, Material
    from live_review.workers.media_artifacts import read_json

    root = Path(env["LIVE_STORAGE_ROOT"])
    key = uuid4()
    path = root / "blobs" / str(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x00" * 35200)
    data = path.read_bytes()
    with Session(engine, expire_on_commit=False) as db:
        workspace = Workspace(name="LIVE-006B registry acceptance")
        db.add(workspace)
        db.flush()
        admin = Admin(
            workspace_id=workspace.id,
            username=uuid4().hex,
            display_name="Synthetic",
            password_hash=hasher.hash(uuid4().hex),
        )
        blob = Blob(
            workspace_id=workspace.id,
            storage_key=key,
            size_bytes=len(data),
            media_type="audio/wav",
            sha256=hashlib.sha256(data).hexdigest(),
        )
        db.add_all([admin, blob])
        db.flush()
        material = Material(
            workspace_id=workspace.id,
            blob_id=blob.id,
            filename="synthetic.wav",
            purpose="session_media",
            created_at=now(),
        )
        db.add(material)
        db.commit()
    cfg = run / "config"
    (cfg / "environments").mkdir(parents=True)
    base = {
        "schema_version": 2,
        "revision": "acceptance-v2",
        "media": {"segment_seconds": 4, "max_duration_seconds": 20},
        "models": {
            "fixture": {
                "capability": "asr",
                "route": {
                    "enabled": True,
                    "protocol": "offline_fixture",
                    "provider": "synthetic",
                    "model": "fixture-v1",
                    "max_requests": 5,
                    "max_cost_usd": 0.0,
                },
            }
        },
        "aliases": {"asr.default": "fixture"},
    }
    (cfg / "models.yaml").write_text(yaml.safe_dump(base))
    (cfg / "environments/development.yaml").write_text("media:\n  segment_seconds: 3\n")
    (cfg / "local.yaml").write_text("media:\n  segment_seconds: 2\n")
    dotenv = run / ".env"
    dotenv.write_text(
        "LIVE_MODEL_SEGMENT_SECONDS=1\nLIVE_MODEL_MAX_DURATION_SECONDS=12\nUNUSED_PRIVATE_VALUE=synthetic-not-a-real-secret\n"
    )
    dotenv.chmod(0o600)
    env["LIVE_MODEL_MAX_DURATION_SECONDS"] = "10"
    fixture = run / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "segments": {
                    str(i): {
                        "utterances": [{"text": "synthetic", "start_ms": 0, "end_ms": 100}],
                        "coverage": "full",
                        "missing_words": False,
                        "no_speech": False,
                    }
                    for i in range(3)
                }
            }
        )
    )
    legacy = run / "legacy.yaml"
    legacy.write_text(
        (ROOT / "infra/providers.offline.example.yaml")
        .read_text()
        .replace("segment_seconds: 300", "segment_seconds: 1")
    )
    results = []
    for label, options in [("v2", ["--config-dir", str(cfg)]), ("v1", ["--config", str(legacy)])]:
        cli = [sys.executable, "-m", "live_review.workers.media_operator"]
        common = ["--workspace-id", str(workspace.id), "--admin-id", str(admin.id)]
        reply = command(
            label + "-submit",
            cli
            + [
                "submit",
                *common,
                "--material-id",
                str(material.id),
                *options,
                "--fixture",
                str(fixture),
            ],
        )
        job_id = UUID(json.loads(reply.strip().splitlines()[-1])["job_id"])
        command(label + "-run", cli + ["run-local", *common, "--job-id", str(job_id)])
        with Session(engine) as db:
            job = db.get(Job, job_id)
            assert job.status == "succeeded", job.error
            payload = job.input_data
            assert payload["provider_snapshot"]["snapshot_version"] == int(label[-1])
            assert "synthetic-not-a-real-secret" not in json.dumps(payload)
            stages = stages_for(db, job_id)
            refs = {s.name: s.artifact for s in stages}
        transcript = read_json(root, refs["asr"])
        assert transcript["complete"] and transcript["synthetic"]
        assert [u["start_ms"] for u in transcript["utterances"]] == [0, 1000, 2000]
        if label == "v2":
            media = payload["provider_snapshot"]["content"]["media"]
            assert (media["segment_seconds"], media["max_duration_seconds"]) == (1, 10)
        results.append(
            {"version": label, "job_id": str(job_id), "input": payload, "artifacts": refs}
        )
    output = run / "result.json"
    output.write_text(
        json.dumps({"jobs": results, "real_model_calls": 0, "synthetic": True}, indent=2)
    )
    print(json.dumps({"status": "passed", "result": str(output)}))


if __name__ == "__main__":
    main()
