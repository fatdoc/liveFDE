"""Create isolated LIVE-005 databases; fixed resources, no drop or external DSN."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

WORKSPACE = Path("/Users/docfat/Desktop/个人/project/直播体系FDE")
ROOT = Path(__file__).resolve().parents[2]
RUNTIME = WORKSPACE / "runtime/live-005"
ROLES = ("be", "qa", "integration", "qa_identity")
CONTAINER = "live-fde-005-postgres-1"


def run(args, *, env, **kwargs):
    return subprocess.run(
        args, env=env, check=True, capture_output=True, text=True, **kwargs
    ).stdout


def safe_parent_environment():
    environment = os.environ.copy()
    for key in environment:
        if key.startswith(("DOCKER_", "COMPOSE_", "RABBITMQ_", "ERL_")) or key in {
            "LIVE_RUNTIME",
            "PG_PASSWORD",
            "MQ_COOKIE",
        }:
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


def provision_postgres(environment, config):
    env = RUNTIME / "private.env"
    environment.update(config)

    def execute(args, **kwargs):
        return run(args, env=environment, **kwargs)

    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env),
        "-f",
        str(ROOT / "infra/compose.live005.yml"),
        "-p",
        "live-fde-005",
    ]
    # Existing fixed-name container must belong to our project and exact bind mount.
    existing = execute(["docker", "ps", "-aq", "--filter", f"name=^/{CONTAINER}$"]).strip()
    if existing:
        info = json.loads(execute(["docker", "inspect", existing]))[0]
        if info["Config"]["Labels"].get("com.docker.compose.project") != "live-fde-005" or not any(
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
                "live005_admin",
                "-d",
                "live005_control",
                "-At",
            ],
            input=statement,
        )

    for suffix in ROLES:
        name = f"live005_{suffix}"
        target = RUNTIME / f"{suffix}.env"
        if target.exists():
            if target.is_symlink() or target.stat().st_mode & 0o077:
                raise SystemExit("Unsafe task env")
            validate_task_env(suffix)
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
        mq_password = secrets.token_hex(24)
        private(
            target,
            f"LIVE_DATABASE_URL=postgresql+psycopg://{name}:{password}@127.0.0.1:15450/{name}\n"
            f"LIVE_BROKER_URL=amqp://{name}:{mq_password}@127.0.0.1:5675/{name}\n"
            f"LIVE_TASK_QUEUE={name}\n"
            f"LIVE_STORAGE_ROOT={RUNTIME / ('storage-' + suffix)}\n",
        )
        sql(
            f"CREATE ROLE {name} LOGIN PASSWORD '{password}';\n"
            f"CREATE DATABASE {name} OWNER {name};\n"
            f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
        )
        print(f"{suffix}: database created; credentials in {target}")
    print("PostgreSQL ready on 127.0.0.1:15450")


MQ_BASE = RUNTIME / "rabbit-native"
MQ_BIN = Path("/opt/homebrew/opt/rabbitmq/sbin")
NODE = "live005@localhost"


def checked_runtime():
    if ROOT != WORKSPACE / "app" and ROOT.parent != WORKSPACE / ".worktrees":
        raise SystemExit("Refusing non-workspace checkout")
    if RUNTIME.resolve() != RUNTIME:
        raise SystemExit("Refusing redirected runtime")
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in RUNTIME.rglob("*"):
        if path.is_symlink():
            raise SystemExit("Refusing runtime symlink")
    private_env = RUNTIME / "private.env"
    if not private_env.exists():
        private(
            private_env,
            f"LIVE_RUNTIME={RUNTIME}\nPG_PASSWORD={secrets.token_hex(24)}\n"
            f"MQ_COOKIE={secrets.token_hex(24)}\n",
        )
    values = read_private(private_env)
    if set(values) != {"LIVE_RUNTIME", "PG_PASSWORD", "MQ_COOKIE"} or (
        values["LIVE_RUNTIME"] != str(RUNTIME)
        or not all(re.fullmatch(r"[0-9a-f]{48}", values[k]) for k in ("PG_PASSWORD", "MQ_COOKIE"))
    ):
        raise SystemExit("Refusing changed runtime config")
    return values


def read_private(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise SystemExit("Private env must be regular and mode 600")
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


def validate_task_env(suffix):
    values = read_private(RUNTIME / f"{suffix}.env")
    name = "live005_" + suffix
    expected = {
        "LIVE_DATABASE_URL",
        "LIVE_BROKER_URL",
        "LIVE_STORAGE_ROOT",
        "LIVE_TASK_QUEUE",
    }
    if (
        set(values) != expected
        or not re.fullmatch(
            rf"postgresql\+psycopg://{name}:[0-9a-f]{{48}}@127\.0\.0\.1:15450/{name}",
            values.get("LIVE_DATABASE_URL", ""),
        )
        or not re.fullmatch(
            rf"amqp://{name}:[0-9a-f]{{48}}@127\.0\.0\.1:5675/{name}",
            values.get("LIVE_BROKER_URL", ""),
        )
        or values.get("LIVE_STORAGE_ROOT") != str(RUNTIME / f"storage-{suffix}")
        or (values.get("LIVE_TASK_QUEUE") != name)
    ):
        raise SystemExit("Refusing changed task destination")
    return values


def rabbit_environment(environment, config):
    return environment | {
        "RABBITMQ_NODENAME": NODE,
        "RABBITMQ_NODE_PORT": "5675",
        "RABBITMQ_DIST_PORT": "25675",
        "RABBITMQ_MNESIA_BASE": str(MQ_BASE / "mnesia"),
        "RABBITMQ_LOG_BASE": str(MQ_BASE / "log"),
        "RABBITMQ_PID_FILE": str(MQ_BASE / "rabbit.pid"),
        "RABBITMQ_CONFIG_FILE": str(MQ_BASE / "rabbitmq.conf"),
        "RABBITMQ_CONF_ENV_FILE": str(MQ_BASE / "env.conf"),
        "RABBITMQ_ENABLED_PLUGINS_FILE": str(MQ_BASE / "enabled_plugins"),
        "RABBITMQ_ERLANG_COOKIE": config["MQ_COOKIE"],
        "RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS": "-kernel inet_dist_use_interface {127,0,0,1}",
        "RABBITMQ_CTL_ERL_ARGS": "-kernel inet_dist_use_interface {127,0,0,1}",
    }


def owned_mq_pid(environment):
    path = MQ_BASE / "rabbit.pid"
    if not path.exists():
        return None
    value = path.read_text().strip()
    if not value.isdigit() or int(value) < 2:
        raise SystemExit("Refusing invalid MQ pid")
    result = subprocess.run(
        ["ps", "-p", value, "-o", "command="],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    command = result.stdout
    files = subprocess.run(
        ["lsof", "-a", "-p", value, "-Fn"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    owned_files = any(
        line.startswith("n" + str(MQ_BASE) + "/") for line in files.stdout.splitlines()
    )
    if "beam.smp" not in command or files.returncode != 0 or not owned_files:
        raise SystemExit("Refusing foreign MQ process")
    return int(value)


def write_mq_config():
    MQ_BASE.mkdir(mode=0o700, exist_ok=True)
    definitions = {"users": [], "vhosts": [], "permissions": []}
    for suffix in ROLES:
        values = validate_task_env(suffix)
        (RUNTIME / f"storage-{suffix}").mkdir(mode=0o700, exist_ok=True)
        parsed = urlsplit(values["LIVE_BROKER_URL"])
        salt = secrets.token_bytes(4)
        hashed = base64.b64encode(salt + hashlib.sha256(salt + parsed.password.encode()).digest())
        definitions["users"].append(
            {
                "name": parsed.username,
                "password_hash": hashed.decode(),
                "hashing_algorithm": "rabbit_password_hashing_sha256",
                "tags": [],
            }
        )
        definitions["vhosts"].append({"name": parsed.username})
        definitions["permissions"].append(
            {
                "user": parsed.username,
                "vhost": parsed.username,
                "configure": ".*",
                "write": ".*",
                "read": ".*",
            }
        )
    # Runtime symlink guard precedes atomic private-file replacement.
    files = {
        "definitions.json": json.dumps(definitions),
        "rabbitmq.conf": "listeners.tcp.1 = 127.0.0.1:5675\n"
        f"definitions.import_backend = local_filesystem\n"
        f"definitions.local.path = {MQ_BASE / 'definitions.json'}\n",
        "env.conf": "",
        "enabled_plugins": "[].\n",
    }
    for name, content in files.items():
        path = MQ_BASE / name
        temp = MQ_BASE / (name + ".tmp-" + secrets.token_hex(6))
        private(temp, content)
        temp.replace(path)


def mq_start(environment, config):
    if owned_mq_pid(environment):
        run(
            [str(MQ_BIN / "rabbitmq-diagnostics"), "-n", NODE, "-q", "check_running"],
            env=rabbit_environment(environment, config),
            timeout=15,
        )
        print("MQ existing owned process healthy and retained")
        return
    for port in (5675, 25675):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(f"Refusing occupied MQ port {port}") from None
    write_mq_config()
    child_environment = rabbit_environment(environment, config)
    with (MQ_BASE / "console.log").open("a") as log:
        process = subprocess.Popen(
            [str(MQ_BIN / "rabbitmq-server")],
            env=child_environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    for _ in range(60):
        if process.poll() is not None:
            raise SystemExit("MQ startup failed; inspect private runtime console log")
        if owned_mq_pid(environment):
            result = subprocess.run(
                [
                    str(MQ_BIN / "rabbitmq-diagnostics"),
                    "-n",
                    NODE,
                    "-q",
                    "check_running",
                ],
                env=child_environment,
                capture_output=True,
                timeout=15,
            )
            if result.returncode == 0:
                print("MQ ready on 127.0.0.1:5675; separate task vhosts")
                return
        time.sleep(1)
    raise SystemExit("MQ startup timeout; inspect owned process before retry")


def mq_stop(environment, config):
    if not owned_mq_pid(environment):
        print("MQ owned process already stopped")
        return
    run(
        [str(MQ_BIN / "rabbitmqctl"), "-n", NODE, "stop"],
        env=rabbit_environment(environment, config),
        timeout=45,
    )
    for _ in range(30):
        if not owned_mq_pid(environment):
            print("MQ owned node stopped; data retained")
            return
        time.sleep(1)
    raise SystemExit("MQ stop incomplete; no forced termination attempted")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["up", "mq-start", "mq-stop", "mq-restart", "pg-stop"],
        nargs="?",
        default="up",
    )
    args = parser.parse_args(argv)
    environment = safe_parent_environment()
    config = checked_runtime()
    for suffix in ROLES:
        if (RUNTIME / f"{suffix}.env").exists():
            validate_task_env(suffix)
    if args.action == "up":
        provision_postgres(environment, config)
        mq_start(environment, config)
    elif args.action in {"mq-start", "mq-stop", "mq-restart"}:
        if args.action != "mq-start":
            mq_stop(environment, config)
        if args.action != "mq-stop":
            mq_start(environment, config)
    elif args.action == "pg-stop":
        info = json.loads(run(["docker", "inspect", CONTAINER], env=environment))[0]
        if info["Config"]["Labels"].get("com.docker.compose.project") != "live-fde-005" or (
            not any(
                m["Source"] == str(RUNTIME / "postgres")
                and m["Destination"] == "/var/lib/postgresql/data"
                for m in info["Mounts"]
            )
        ):
            raise SystemExit("Refusing foreign container")
        run(["docker", "stop", CONTAINER], env=environment)
        print("PG owned container stopped; data retained")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Command failed; inspect private runtime state (credentials withheld)"
        ) from None
