"""Isolated LIVE-006C development resources; never reuse another round's database."""

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
RUNTIME = WORKSPACE / "runtime/live-006c"


def environment():
    if WORKSPACE != Path("/Users/docfat/Desktop/个人/project/直播体系FDE"):
        raise RuntimeError("unregistered_workspace")
    path = RUNTIME / "private.env"
    if path.resolve() != path:
        raise RuntimeError("unsafe_environment_path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as handle:
        info = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_size > 8192
        ):
            raise RuntimeError("unsafe_environment_file")
        lines = handle.read(8193).splitlines()
    values = dict(line.split("=", 1) for line in lines)
    expected = {
        "LIVE_RUNTIME",
        "PG_PASSWORD",
        "LIVE_DATABASE_URL",
        "LIVE_BROKER_URL",
        "LIVE_STORAGE_ROOT",
    }
    if len(lines) != len(values) or set(values) != expected:
        raise RuntimeError("invalid_environment")
    password = values["PG_PASSWORD"]
    if (
        not re.fullmatch("[a-f0-9]{48}", password)
        or values["LIVE_DATABASE_URL"]
        != f"postgresql+psycopg://live006c:{password}@127.0.0.1:15480/live006c"
        or values["LIVE_RUNTIME"] != str(RUNTIME)
        or values["LIVE_STORAGE_ROOT"] != str(RUNTIME / "storage")
        or values["LIVE_BROKER_URL"] != "amqp://unconfigured:unconfigured@127.0.0.1:1//"
    ):
        raise RuntimeError("foreign_destination")
    env = {k: v for k, v in os.environ.items() if not k.startswith("LIVE_")}
    env.update({k: v for k, v in values.items() if k.startswith("LIVE_")})
    env.update(LIVE_ENVIRONMENT="development", LIVE_JOB_TEST_HANDLERS="false")
    return env


def new_database(env, label):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    if label not in {"ui", "suite", "qa", "smoke"}:
        raise RuntimeError("unknown_database_label")
    name = f"live006c_{label}_{uuid4().hex}"
    control = create_engine(env["LIVE_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with control.connect() as connection:
        if connection.execute(
            text("SELECT current_database(), current_user")
        ).one() != ("live006c", "live006c"):
            raise RuntimeError("unexpected_control_database")
        connection.execute(text(f'CREATE DATABASE "{name}" OWNER live006c'))
    control.dispose()
    env["LIVE_DATABASE_URL"] = (
        make_url(env["LIVE_DATABASE_URL"])
        .set(database=name)
        .render_as_string(hide_password=False)
    )
    env["LIVE_TEST_DATABASE_URL"] = env["LIVE_DATABASE_URL"]
    target = create_engine(env["LIVE_DATABASE_URL"])
    try:
        with target.connect() as connection:
            if connection.execute(
                text("SELECT current_database(), current_user")
            ).one() != (name, "live006c"):
                raise RuntimeError("unexpected_test_database")
    finally:
        target.dispose()
    return name


def init_ui():
    import secrets

    import yaml
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from live_review.modules.identity.models import Admin, Workspace
    from live_review.modules.identity.security import hasher

    env = environment()
    if (RUNTIME / "ui.env").exists():
        raise RuntimeError("ui_environment_already_exists_do_not_replace")
    database = new_database(env, "ui")
    cfg = RUNTIME / "config"
    cfg.mkdir(exist_ok=True)
    values = yaml.safe_load((ROOT / "config/asr.example.yaml").read_text())
    values["models"]["local_funasr"]["route"].update(
        enabled=True,
        model_root=str(RUNTIME / "models"),
        device="cpu",
        punctuation_model="ct-punc",
        worker_socket=str(RUNTIME / "asr.sock"),
    )
    # Enabled profile is not authorization; task grants and budgets still gate requests.
    values["models"]["tencent_asr"]["route"]["enabled"] = True
    (cfg / "models.yaml").write_text(yaml.safe_dump(values))
    env.update(
        LIVE_MODEL_CONFIG_DIR=str(cfg),
        LIVE_ASR_BACKGROUND_RUNNER="true",
        LIVE_TRUSTED_ORIGINS='["http://127.0.0.1:5196","http://localhost:5196"]',
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "services/backend",
        env=env,
        check=True,
        capture_output=True,
    )
    engine = create_engine(env["LIVE_DATABASE_URL"])
    username, password = "asr-demo-" + uuid4().hex[:8], secrets.token_urlsafe(18)
    with Session(engine) as db:
        workspace = Workspace(name="LIVE-006C合成验收工作区")
        db.add(workspace)
        db.flush()
        db.add(
            Admin(
                workspace_id=workspace.id,
                username=username,
                display_name="ASR验收管理员",
                password_hash=hasher.hash(password),
            )
        )
        db.commit()
    engine.dispose()
    for file, content in (
        (
            "ui.env",
            "\n".join(f"{k}={v}" for k, v in env.items() if k.startswith("LIVE_"))
            + "\n",
        ),
        (
            "ui-account.json",
            json.dumps(
                {
                    "username": username,
                    "password": password,
                    "synthetic": True,
                    "database": database,
                }
            ),
        ),
    ):
        fd = os.open(RUNTIME / file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
    print(
        "Isolated UI DB migrated; synthetic login in runtime/live-006c/ui-account.json"
    )


if __name__ == "__main__":
    init_ui()
