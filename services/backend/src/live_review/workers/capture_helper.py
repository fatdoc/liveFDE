"""Local authenticated capture client. Start the existing runner, stop via API on Ctrl-C.

Run with the same isolated backend environment as capture_operator. This is a
command-line client for the reusable API, not a new provider or queue.
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["douyin", "wechat"], required=True)
    parser.add_argument("--source-ref", help="Douyin PC room URL; WeChat uses phone_cast")
    parser.add_argument("--session-id")
    parser.add_argument("--account-file", type=Path, help="Private local JSON; never sent to API")
    parser.add_argument("--username")
    parser.add_argument("--origin", default="http://127.0.0.1:5188")
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--api", default="http://127.0.0.1:8197")
    args = parser.parse_args()
    # Local operator starts a local runner. Prevent accidentally logging into another host.
    if args.api != "http://127.0.0.1:8197":
        parser.error("This local helper is registered for 127.0.0.1:8197")
    if args.account_file:
        if args.account_file.is_symlink() or args.account_file.stat().st_mode & 0o077:
            parser.error("Account file must be private (0600), not a symlink")
        account = json.loads(args.account_file.read_text())
        username, password = account["username"], account["password"]
        session_id = args.session_id or account.get("sessions", {}).get(args.platform)
    else:
        username = args.username or input("Username: ")
        password = getpass.getpass("Password: ")
        session_id = args.session_id
    if not session_id or (args.platform == "douyin" and not args.source_ref):
        parser.error("session-id and a Douyin PC room source-ref are required")
    headers = {"Origin": args.origin, "Sec-Fetch-Site": "same-origin"}
    with httpx.Client(base_url=args.api, timeout=30, trust_env=False) as client:
        login = client.post(
            "/api/v1/auth/login", headers=headers, json={"username": username, "password": password}
        )
        if login.status_code != 200:
            raise SystemExit("login_failed")
        headers["X-CSRF-Token"] = login.json()["csrf_token"]
        headers["Idempotency-Key"] = args.idempotency_key or str(uuid4())
        response = client.post(
            "/api/v1/capture/runs",
            headers=headers,
            json={
                "platform": args.platform,
                "session_id": session_id,
                "source_ref": args.source_ref if args.platform == "douyin" else "phone_cast",
            },
        )
        if response.status_code != 202:
            raise SystemExit(response.json().get("code", "start_failed"))
        run = response.json()
        print(
            json.dumps(
                {
                    "capture_run_id": run["capture_run_id"],
                    "job_id": run["job_id"],
                    "idempotency_key": headers["Idempotency-Key"],
                }
            ),
            flush=True,
        )
        worker = subprocess.Popen(
            [sys.executable, "-m", "live_review.workers.capture_operator", run["job_id"]],
            start_new_session=True,
            env=os.environ.copy(),
        )
        path = "/api/v1/capture/runs/" + run["capture_run_id"]
        previous = None
        while True:
            try:
                response = client.get(path)
                response.raise_for_status()
                state = response.json()
                if state["state"] != previous:
                    print(
                        json.dumps({"state": state["state"], "error_code": state["error_code"]}),
                        flush=True,
                    )
                    previous = state["state"]
                if state["job_status"] in {"succeeded", "failed", "canceled"}:
                    print(json.dumps(state, ensure_ascii=False), flush=True)
                    worker.wait(timeout=10)
                    return
                if worker.poll() is not None:
                    raise SystemExit(
                        "worker_exited_before_terminal_state; query/recover existing job"
                    )
                time.sleep(0.5)
            except KeyboardInterrupt:
                stopped = client.post(path + "/stop", headers=headers)
                stopped.raise_for_status()
                print("Stop requested; waiting for closed media and import.", flush=True)


if __name__ == "__main__":
    main()
