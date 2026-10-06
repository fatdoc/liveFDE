"""Provision the one isolated LIVE-006B media job acceptance database; never reset data."""

import json
import os
import re
import secrets
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

WORKSPACE = Path("/Users/docfat/Desktop/个人/project/直播体系FDE")
ROOT = Path(__file__).resolve().parents[2]
RUNTIME = WORKSPACE / "runtime/live-006b"
CONTAINER = "live-fde-006b-postgres-1"


def main():
    if ROOT != WORKSPACE / "app" or RUNTIME.resolve() != RUNTIME:
        raise SystemExit("Refusing unregistered checkout or redirected runtime")
    environment = os.environ.copy()
    if any(
        k.startswith(("DOCKER_", "COMPOSE_")) or k in ("PG_PASSWORD", "LIVE_RUNTIME")
        for k in environment
    ):
        raise SystemExit("Refusing inherited resource overrides")
    endpoint = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
    ).strip()
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "unix"
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit("Refusing nonlocal Docker context")
    environment["DOCKER_HOST"] = endpoint
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = RUNTIME / "private.env"
    if not path.exists():
        password = secrets.token_hex(24)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(
                f"LIVE_RUNTIME={RUNTIME}\nPG_PASSWORD={password}\n"
                f"LIVE_DATABASE_URL=postgresql+psycopg://live006b:{password}"
                "@127.0.0.1:15470/live006b\n"
                "LIVE_BROKER_URL=amqp://unconfigured:unconfigured@127.0.0.1:1//\n"
                f"LIVE_STORAGE_ROOT={RUNTIME / 'storage'}\n"
            )
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8192:
                raise SystemExit("Refusing unsafe credentials file")
            payload = source.read(8193)
            if len(payload) > 8192:
                raise SystemExit("Refusing unsafe credentials file")
        lines = payload.splitlines()
        values = dict(line.split("=", 1) for line in lines)
    except (ValueError, OSError):
        raise SystemExit("Refusing invalid private environment") from None
    if len(lines) != len(values) or set(values) != {
        "LIVE_RUNTIME",
        "PG_PASSWORD",
        "LIVE_DATABASE_URL",
        "LIVE_BROKER_URL",
        "LIVE_STORAGE_ROOT",
    }:
        raise SystemExit("Refusing unexpected private environment fields")
    password = values.get("PG_PASSWORD", "")
    if (
        not re.fullmatch("[0-9a-f]{48}", password)
        or values.get("LIVE_RUNTIME") != str(RUNTIME)
        or values.get("LIVE_STORAGE_ROOT") != str(RUNTIME / "storage")
        or values.get("LIVE_DATABASE_URL")
        != f"postgresql+psycopg://live006b:{password}@127.0.0.1:15470/live006b"
        or values.get("LIVE_BROKER_URL") != "amqp://unconfigured:unconfigured@127.0.0.1:1//"
        or any(p.is_symlink() for p in RUNTIME.rglob("*"))
    ):
        raise SystemExit("Refusing changed task destination")
    environment.update(values)

    def run(args):
        return subprocess.check_output(args, env=environment, text=True, stderr=subprocess.PIPE)

    exists = run(["docker", "ps", "-aq", "--filter", f"name=^/{CONTAINER}$"]).strip()
    if exists:
        info = json.loads(run(["docker", "inspect", exists]))[0]
        if info["Config"]["Labels"].get("com.docker.compose.project") != "live-fde-006b" or not any(
            m["Source"] == str(RUNTIME / "postgres")
            and m["Destination"] == "/var/lib/postgresql/data"
            for m in info["Mounts"]
        ):
            raise SystemExit("Refusing foreign container")
    run(
        [
            "docker",
            "compose",
            "-p",
            "live-fde-006b",
            "--env-file",
            str(path),
            "-f",
            str(ROOT / "infra/compose.live006b.yml"),
            "up",
            "-d",
            "--wait",
            "postgres",
        ]
    )
    print("LIVE-006B isolated PG15470 ready; original databases untouched; no broker started")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit("Provision failed; private values withheld") from None
