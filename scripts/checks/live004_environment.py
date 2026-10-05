"""Create isolated LIVE-004 databases; fixed resources, no drop or external DSN."""

import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

WORKSPACE = Path("/Users/docfat/Desktop/个人/project/直播体系FDE")
ROOT = Path(__file__).resolve().parents[2]
RUNTIME = WORKSPACE / "runtime/live-004"
ROLES = ("4a", "4b", "4c", "qa", "integration")
CONTAINER = "live-fde-004-postgres-1"


def run(args, *, env, **kwargs):
    return subprocess.run(
        args, env=env, check=True, capture_output=True, text=True, **kwargs
    ).stdout


def safe_parent_environment():
    environment = os.environ.copy()
    for key in environment:
        if key.startswith(("DOCKER_", "COMPOSE_")) or key in {"LIVE_RUNTIME", "PG_PASSWORD"}:
            raise SystemExit(f"Refusing inherited override {key}")
    endpoint = run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        env=environment,
    ).strip()
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "unix"
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit("Refusing non-local Docker context")
    # Pin the verified endpoint for all later Docker calls, even if active context changes.
    environment["DOCKER_HOST"] = endpoint
    return environment


def private(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)


def main():
    environment = safe_parent_environment()
    if ROOT != WORKSPACE / "app" and ROOT.parent != WORKSPACE / ".worktrees":
        raise SystemExit("Refusing non-workspace checkout")
    if RUNTIME.resolve() != RUNTIME:
        raise SystemExit("Refusing redirected runtime")
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = RUNTIME / "private.env"
    if not env.exists():
        private(env, f"LIVE_RUNTIME={RUNTIME}\nPG_PASSWORD={secrets.token_hex(24)}\n")
    elif env.is_symlink() or env.stat().st_mode & 0o077:
        raise SystemExit("Private env must be regular and mode 600")
    config = dict(line.split("=", 1) for line in env.read_text().splitlines())
    if (
        set(config) != {"LIVE_RUNTIME", "PG_PASSWORD"}
        or config.get("LIVE_RUNTIME") != str(RUNTIME)
        or not re.fullmatch(r"[0-9a-f]{48}", config.get("PG_PASSWORD", ""))
        or (RUNTIME / "postgres").is_symlink()
    ):
        raise SystemExit("Refusing changed runtime")
    # Explicit values beat inherited shell interpolation and come only from checked file.
    environment.update(config)

    def execute(args, **kwargs):
        return run(args, env=environment, **kwargs)

    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env),
        "-f",
        str(ROOT / "infra/compose.live004.yml"),
        "-p",
        "live-fde-004",
    ]
    # Existing fixed-name container must belong to our project and exact bind mount.
    existing = execute(["docker", "ps", "-aq", "--filter", f"name=^/{CONTAINER}$"]).strip()
    if existing:
        info = json.loads(execute(["docker", "inspect", existing]))[0]
        if info["Config"]["Labels"].get("com.docker.compose.project") != "live-fde-004" or not any(
            m["Source"] == str(RUNTIME / "postgres")
            and m["Destination"] == "/var/lib/postgresql/data"
            for m in info["Mounts"]
        ):
            raise SystemExit("Refusing foreign container")
    execute(compose + ["up", "-d", "--wait", "postgres"])

    def sql(statement):
        return execute(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "live004_admin",
                "-d",
                "live004_control",
                "-At",
            ],
            input=statement,
        )

    for suffix in ROLES:
        name = f"live004_{suffix}"
        target = RUNTIME / f"{suffix}.env"
        if target.exists():
            if target.is_symlink() or target.stat().st_mode & 0o077:
                raise SystemExit("Unsafe task env")
            values = dict(line.split("=", 1) for line in target.read_text().splitlines())
            expected = (
                rf"postgresql\+psycopg://{name}:[0-9a-f]{{48}}"
                rf"@127\.0\.0\.1:15440/{name}"
            )
            if not re.fullmatch(expected, values.get("LIVE_DATABASE_URL", "")) or values.get(
                "LIVE_STORAGE_ROOT"
            ) != str(RUNTIME / ("storage-" + suffix)):
                raise SystemExit("Refusing changed task destination")
            if (
                sql(
                    f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{name}';"
                ).strip()
                != name
            ):
                raise SystemExit(
                    f"{name}: database missing or wrong owner; manual recovery required"
                )
            print(f"{suffix}: existing env retained; no database mutation")
            continue
        if (
            sql(f"SELECT 1 FROM pg_roles WHERE rolname='{name}';").strip()
            or sql(f"SELECT 1 FROM pg_database WHERE datname='{name}';").strip()
        ):
            raise SystemExit(f"{name} exists without private env; refusing mutation")
        password = secrets.token_hex(24)
        private(
            target,
            f"LIVE_DATABASE_URL=postgresql+psycopg://{name}:{password}@127.0.0.1:15440/{name}\n"
            "LIVE_BROKER_URL=amqp://unconfigured:unconfigured@127.0.0.1:1//\n"
            f"LIVE_STORAGE_ROOT={RUNTIME / ('storage-' + suffix)}\n",
        )
        sql(
            f"CREATE ROLE {name} LOGIN PASSWORD '{password}';\n"
            f"CREATE DATABASE {name} OWNER {name};\n"
            f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
        )
        print(f"{suffix}: database created; credentials in {target}")
    print("PostgreSQL ready on 127.0.0.1:15440; broker intentionally unavailable")


if __name__ == "__main__":
    main()
