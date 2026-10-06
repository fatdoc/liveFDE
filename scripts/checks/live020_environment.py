"""Run commands against the registered isolated LIVE-020 runtime, without echoing secrets."""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent.parent if ROOT.parent.name == ".worktrees" else ROOT.parent
RUNTIME = WORKSPACE / "runtime/live-020"


def environment():
    path = RUNTIME / "private.env"
    if RUNTIME.resolve() != RUNTIME:
        raise RuntimeError("unsafe_runtime")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_size > 8192
        ):
            raise RuntimeError("unsafe_private_config")
        lines = stream.read(8193).splitlines()
    values = dict(line.split("=", 1) for line in lines)
    expected = {
        "LIVE_DATABASE_URL",
        "LIVE_BROKER_URL",
        "LIVE_STORAGE_ROOT",
        "LIVE_MODEL_CONFIG_DIR",
    }
    if len(values) != len(lines) or set(values) != expected:
        raise RuntimeError("invalid_private_config")
    if (
        not re.fullmatch(
            r"postgresql\+psycopg://live020:[a-f0-9]{48}@127\.0\.0\.1:15500/live020",
            values["LIVE_DATABASE_URL"],
        )
        or values["LIVE_BROKER_URL"] != "amqp://unconfigured:unconfigured@127.0.0.1:1//"
        or values["LIVE_STORAGE_ROOT"] != str(RUNTIME / "storage")
        or values["LIVE_MODEL_CONFIG_DIR"] != str(RUNTIME / "config")
    ):
        raise RuntimeError("foreign_destination")
    env = {k: v for k, v in os.environ.items() if not k.startswith("LIVE_")}
    env.update(values)
    env["LIVE_TRUSTED_ORIGINS"] = '["http://127.0.0.1:5199","http://localhost:5199"]'
    env["LIVE_ENVIRONMENT"] = "development"
    if "LIVE_CAPTURE_DOUYIN_COOKIE" in os.environ:
        env["LIVE_CAPTURE_DOUYIN_COOKIE"] = os.environ["LIVE_CAPTURE_DOUYIN_COOKIE"]
    env["PYTHONPATH"] = str(ROOT / "services/backend/src")
    return env


def configure_database():
    from sqlalchemy import create_engine, text

    env = environment()
    engine = create_engine(env["LIVE_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        if conn.execute(text("select current_database(), current_user")).one() != (
            "live020",
            "live020",
        ):
            raise RuntimeError("foreign_database")
        conn.execute(text("ALTER DATABASE live020 SET timezone TO 'UTC'"))
    engine.dispose()
    with engine.connect() as conn:
        print(
            {
                "database": "live020",
                "user": "live020",
                "timezone": conn.execute(text("SHOW TimeZone")).scalar(),
            }
        )
    engine.dispose()


if __name__ == "__main__":
    if sys.argv[1:] == ["--configure-db"]:
        configure_database()
        raise SystemExit(0)
    env = environment()
    child = subprocess.Popen(sys.argv[1:], env=env, cwd=ROOT / "services/backend")
    while True:
        try:
            raise SystemExit(child.wait())
        except KeyboardInterrupt:
            # The same terminal signal reaches the child. Let its stop handshake finish.
            continue
