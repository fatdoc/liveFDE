"""Destructive only to this task's isolated compose services; never delete volumes."""

import argparse
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    for line in args.env_file.read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key] = value
    runtime = Path(env["LIVE_RUNTIME"]).resolve()
    workspace = root.parent.parent if root.parent.name == ".worktrees" else root.parent
    if runtime != (workspace / "runtime/live-002").resolve():
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

    def check(path, expected):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8188" + path, timeout=10
                ) as response:
                    code, body = response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                code, body = exc.code, json.load(exc)
            except (OSError, TimeoutError):
                time.sleep(0.5)
                continue
            if code == expected:
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

    try:
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
            json.loads(
                run([str(python), "-m", "live_review.workers.dispatcher", "--check"])
            )
        )
        stop(api)
        api = start(api_args, "api-restart.log")
        check("/health/ready", 200)
        stop(worker)
        worker = start(worker_args, "worker-restart.log")
        time.sleep(3)
        worker_ping()
        for service in ["postgres", "rabbitmq"]:
            run([*compose, "stop", service])
            check("/health/live", 200)
            check("/health/ready", 503)
            run([*compose, "up", "-d", "--wait", service])
            check("/health/ready", 200)
        (runtime / "smoke-results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
    finally:
        # Restore only project-owned dependencies; preserve all bind-mounted data.
        subprocess.run(
            [*compose, "up", "-d", "--wait"], env=env, capture_output=True, check=False
        )
        for process in processes:
            if process.poll() is None:
                stop(process)
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
