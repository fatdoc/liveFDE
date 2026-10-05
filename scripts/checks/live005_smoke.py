"""Isolated real HTTP/PG/MQ process recovery acceptance; synthetic jobs only."""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path("/Users/docfat/Desktop/个人/project/直播体系FDE")
RUNTIME = WORKSPACE / "runtime/live-005"
PORT = 8195
ORIGIN = {"Origin": "http://127.0.0.1:5188", "Sec-Fetch-Site": "same-origin"}


def environment():
    if ROOT != WORKSPACE / "app":
        raise SystemExit("Run acceptance from registered product checkout")
    path = RUNTIME / "integration.env"
    if path.resolve() != path or path.stat().st_mode & 0o077:
        raise SystemExit("Unsafe integration environment file")
    values = dict(line.split("=", 1) for line in path.read_text().splitlines() if line)
    db = urlsplit(values["LIVE_DATABASE_URL"])
    mq = urlsplit(values["LIVE_BROKER_URL"])
    if (
        (db.scheme, db.hostname, db.port, db.username, db.path)
        != ("postgresql+psycopg", "127.0.0.1", 15450, "live005_integration", "/live005_integration")
        or db.query
        or db.fragment
    ):
        raise SystemExit("Refusing non-integration DB")
    if (
        (mq.scheme, mq.hostname, mq.port, mq.username, mq.path)
        != ("amqp", "127.0.0.1", 5675, "live005_integration", "/live005_integration")
        or mq.query
        or mq.fragment
    ):
        raise SystemExit("Refusing external broker")
    storage = Path(values["LIVE_STORAGE_ROOT"])
    if storage != RUNTIME / "storage-integration" or storage.resolve() != storage:
        raise SystemExit("Refusing redirected storage")
    result = os.environ.copy()
    for key in list(result):
        if key.startswith("LIVE_"):
            del result[key]
    result.update(values)
    result.update(
        LIVE_ENVIRONMENT="development",
        LIVE_JOB_TEST_HANDLERS="true",
        LIVE_JOB_LEASE_SECONDS="4",
        LIVE_JOB_DISPATCH_INTERVAL_SECONDS="0.2",
        LIVE_LOGIN_LIMIT="100",
        LIVE_TRUSTED_ORIGINS=json.dumps([ORIGIN["Origin"]]),
    )
    return result


class Harness:
    def __init__(self, env):
        self.env = env
        self.processes = []
        self.logs = []
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", trust_env=False, timeout=10)
        self.results = {"synthetic_handlers": True, "video_analysis": False, "checks": []}
        self.api = None

    def command(self, *args, input=None):
        run = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT / "services/backend",
            env=self.env,
            input=input,
            capture_output=True,
            text=True,
        )
        if run.returncode:
            (RUNTIME / "last-command-failure.log").write_text(run.stdout + run.stderr)
            # Never print inherited URLs/passwords or provider-shaped exceptions.
            raise RuntimeError("Acceptance command failed: " + " ".join(args[:2]))
        return run.stdout

    def start(self, label, *args):
        log = (RUNTIME / f"{label}.log").open("w")
        self.logs.append(log)
        process = subprocess.Popen(
            [sys.executable, *args],
            cwd=ROOT / "services/backend",
            env=self.env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        self.processes.append(process)
        return process

    def stop(self, process, hard=False):
        if process is None:
            return
        # Children can remain in this registered group after the parent was killed.
        try:
            os.killpg(process.pid, signal.SIGKILL if hard else signal.SIGTERM)
        except ProcessLookupError:
            process.wait(timeout=1)
            return
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)

    def start_api(self):
        self.api = self.start(
            "api",
            "-m",
            "uvicorn",
            "live_review.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        )

        def healthy():
            if self.api.poll() is not None:
                raise RuntimeError("API exited before readiness")
            try:
                return self.client.get("/health/live").status_code == 200
            except httpx.TransportError:
                return False

        self.until(healthy, "API startup")

    @staticmethod
    def until(check, label, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = check()
            if result:
                return result
            time.sleep(0.15)
        raise AssertionError("Timed out: " + label)

    def record(self, name):
        self.results["checks"].append(name)
        print("PASS " + name, flush=True)

    def close(self):
        for process in reversed(self.processes):
            self.stop(process)
        # Handler children use their own setsid group. The watchdog is under test,
        # so its success must not be required for acceptance cleanup.
        for log in self.logs:
            log.flush()
            recorded = Path(log.name).read_text(errors="replace")
            for value in re.findall(r"handler_started job=[0-9a-f-]+ pid=(\d+)", recorded):
                pid = int(value)
                check = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command="],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if check.returncode or "multiprocessing.spawn" not in check.stdout:
                    continue
                try:
                    if os.getpgid(pid) == pid:
                        os.killpg(pid, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            log.close()
        self.client.close()


def main():
    env = environment()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    os.environ.update({k: v for k, v in env.items() if k.startswith("LIVE_")})
    harness = Harness(env)
    try:
        from live005_scenarios import run_scenarios

        run_scenarios(harness)
        (RUNTIME / "integration-results.json").write_text(
            json.dumps(harness.results, indent=2) + "\n"
        )
    finally:
        harness.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
