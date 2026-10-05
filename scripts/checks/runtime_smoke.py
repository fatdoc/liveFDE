"""Destructive only to this task's isolated compose services; never delete volumes."""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--native-rabbit", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    for key in ("COMPOSE_PROJECT_NAME", "COMPOSE_FILE", "DOCKER_HOST", "DOCKER_CONTEXT"):
        if env.get(key):
            raise SystemExit(f"Refusing inherited {key}")
    for line in args.env_file.read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key not in {
                "LIVE_RUNTIME",
                "PG_PASSWORD",
                "MQ_PASSWORD",
                "LIVE_DATABASE_URL",
                "LIVE_BROKER_URL",
            }:
                raise SystemExit(f"Unsupported environment field {key}")
            env[key] = value
    for key in ("PG_PASSWORD", "MQ_PASSWORD"):
        if not re.fullmatch(r"[A-Za-z0-9]{24,}", env[key]):
            raise SystemExit(f"Invalid generated {key}")
    for key, scheme, port, path in [
        ("LIVE_DATABASE_URL", "postgresql+psycopg", 15432, "/live002"),
        ("LIVE_BROKER_URL", "amqp", 5673, "//"),
    ]:
        url = urlsplit(env[key])
        if (
            (url.scheme, url.hostname, url.port, url.username, url.path)
            != (scheme, "127.0.0.1", port, "live002", path)
            or url.query
            or url.fragment
        ):
            raise SystemExit(f"Refusing non-isolated {key}")
        expected = env["PG_PASSWORD" if key == "LIVE_DATABASE_URL" else "MQ_PASSWORD"]
        if url.password != expected:
            raise SystemExit(f"Password mismatch for {key}")
    for key in ("COMPOSE_PROJECT_NAME", "COMPOSE_FILE", "DOCKER_HOST", "DOCKER_CONTEXT"):
        if env.get(key):
            raise SystemExit(f"Refusing override {key}")
    endpoint = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        env=env,
        text=True,
    ).strip()
    if not endpoint.startswith("unix://"):
        raise SystemExit("Refusing non-local Docker context")
    runtime = Path(env["LIVE_RUNTIME"]).resolve()
    workspace = root.parent.parent if root.parent.name == ".worktrees" else root.parent
    if runtime != workspace / "runtime/live-002":
        raise SystemExit("Refusing non LIVE-002 runtime")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8188))
    backend = root / "services/backend"
    python = backend / ".venv/bin/python"
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(args.env_file.resolve()),
        "-f",
        str(root / "infra/compose.yaml"),
    ]
    native = None
    processes = []
    handles = []
    results = []

    def run(command, cwd=backend):
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, check=False
        )
        if result.returncode:
            # Do not echo potential DSNs or provider secrets in failure traces.
            raise RuntimeError(f"Command failed: {command[0]} exit={result.returncode}")
        return result.stdout.strip()

    def start(module_args, log):
        handle = (runtime / log).open("w")
        handles.append(handle)
        process = subprocess.Popen(
            [str(python), *module_args],
            cwd=backend,
            env=env,
            stdout=handle,
            stderr=handle,
        )
        processes.append(process)
        return process

    def stop(process):
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def check(path, expected, failed=None):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8188" + path, timeout=10) as response:
                    code, body = response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                code, body = exc.code, json.load(exc)
            except (OSError, TimeoutError):
                time.sleep(0.5)
                continue
            if code == expected:
                if failed:
                    expected_checks = {"database": "up", "broker": "up", failed: "down"}
                    if body.get("checks") != expected_checks:
                        raise AssertionError(f"Wrong failed dependency: {body}")
                results.append({"path": path, "expected": expected, "body": body})
                return
            time.sleep(0.5)
        raise AssertionError(f"{path} did not reach {expected}")

    def worker_ping():
        for _ in range(15):
            output = subprocess.run(
                [
                    str(python),
                    "-m",
                    "celery",
                    "-A",
                    "live_review.workers.celery_app",
                    "inspect",
                    "ping",
                    "--timeout=2",
                    "--destination=live002@foundation",
                ],
                cwd=backend,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            if "pong" in output:
                results.append({"worker": "pong"})
                return
            time.sleep(1)
        raise AssertionError("No worker pong")

    def native_start():
        nonlocal native
        base = runtime / "rabbit-native"
        base.mkdir(exist_ok=True)
        config = base / "rabbitmq.conf"
        config.write_text(
            "listeners.tcp.1 = 127.0.0.1:5673\n"
            f"default_user = live002\ndefault_pass = {env['MQ_PASSWORD']}\n"
        )
        config.chmod(0o600)
        (base / "env.conf").touch()
        native_env = {k: v for k, v in env.items() if not k.startswith(("RABBITMQ_", "ERL_"))} | {
            "RABBITMQ_NODENAME": "live002@localhost",
            "RABBITMQ_NODE_PORT": "5673",
            "RABBITMQ_DIST_PORT": "25673",
            "RABBITMQ_MNESIA_BASE": str(base / "mnesia"),
            "RABBITMQ_LOG_BASE": str(base / "log"),
            "RABBITMQ_PID_FILE": str(base / "rabbit.pid"),
            "RABBITMQ_CONFIG_FILE": str(config),
            "RABBITMQ_CONF_ENV_FILE": str(base / "env.conf"),
            "RABBITMQ_ENABLED_PLUGINS_FILE": str(base / "enabled_plugins"),
            "RABBITMQ_ERLANG_COOKIE": env["MQ_PASSWORD"],
            "RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS": "-kernel inet_dist_use_interface {127,0,0,1}",
        }
        handle = (base / "console.log").open("a")
        handles.append(handle)
        native = subprocess.Popen(
            [str(args.native_rabbit)],
            env=native_env,
            stdout=handle,
            stderr=handle,
            start_new_session=True,
        )

    def native_stop():
        if native is not None and native.poll() is None:
            os.killpg(native.pid, signal.SIGTERM)
            native.wait(timeout=30)

    try:
        if args.native_rabbit:
            for port in (5673, 25673):
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", port))
            run([*compose, "up", "-d", "--wait", "postgres"])
            native_start()
        else:
            run([*compose, "up", "-d", "--wait"])
        run([str(python), "-m", "alembic", "upgrade", "head"])
        results.append({"alembic": "upgrade head successful; no business revisions"})
        api_args = [
            "-m",
            "uvicorn",
            "live_review.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8188",
        ]
        api = start(api_args, "api.log")
        check("/health/live", 200)
        check("/health/ready", 200)
        worker_args = [
            "-m",
            "celery",
            "-A",
            "live_review.workers.celery_app",
            "worker",
            "--pool=solo",
            "--hostname=live002@foundation",
            "--loglevel=WARNING",
        ]
        worker = start(worker_args, "worker.log")
        time.sleep(3)
        worker_ping()
        results.append(
            json.loads(run([str(python), "-m", "live_review.workers.dispatcher", "--check"]))
        )
        stop(api)
        api = start(api_args, "api-restart.log")
        check("/health/ready", 200)
        stop(worker)
        worker = start(worker_args, "worker-restart.log")
        time.sleep(3)
        worker_ping()
        for service in ["postgres", "rabbitmq"]:
            if service == "rabbitmq" and args.native_rabbit:
                native_stop()
            else:
                run([*compose, "stop", service])
            check("/health/live", 200)
            check("/health/ready", 503, "database" if service == "postgres" else "broker")
            if service == "rabbitmq" and args.native_rabbit:
                native_start()
            else:
                run([*compose, "up", "-d", "--wait", service])
            check("/health/ready", 200)
        (runtime / "smoke-results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
    finally:
        # Restore only project-owned dependencies; preserve all bind-mounted data.
        subprocess.run(
            [*compose, "up", "-d", "--wait", *(["postgres"] if args.native_rabbit else [])],
            env=env,
            capture_output=True,
            check=False,
        )
        native_stop()
        for process in processes:
            if process.poll() is None:
                stop(process)
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
