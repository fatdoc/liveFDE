"""Run the real-PG suite with an explicit, narrowly scoped test environment."""

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    workspace = root.parent.parent if root.parent.name == ".worktrees" else root.parent
    runtime = workspace / "runtime"
    path = args.env_file.resolve()
    environment = os.environ.copy()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        expected = runtime / "live-002/private.env"
        username, port = "live002", 15432
        storage = runtime / "live-002/test-materials"
    else:
        expected = runtime / "live-004/qa.env"
        username, port = "live004_qa", 15440
        storage = runtime / "live-004/storage-qa"
    if path != expected or args.env_file.is_symlink():
        raise SystemExit("Only the registered isolated suite environment is allowed")
    for line in path.read_text().splitlines():
        key, value = line.split("=", 1)
        environment[key] = value
    url = urlsplit(environment["LIVE_DATABASE_URL"])
    if (
        (url.scheme, url.hostname, url.port, url.username, url.path)
        != ("postgresql+psycopg", "127.0.0.1", port, username, "/" + username)
        or url.query
        or url.fragment
    ):
        raise SystemExit("Refusing a non-test database")
    if storage.resolve() != storage:
        raise SystemExit("Refusing redirected test storage")
    environment["LIVE_TEST_DATABASE_URL"] = environment["LIVE_DATABASE_URL"]
    environment["LIVE_STORAGE_ROOT"] = str(storage)
    report = path.parent / "pytest-results.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "services/backend/tests",
            "-q",
            f"--junitxml={report}",
        ],
        cwd=root,
        env=environment,
        check=False,
    )
    if result.returncode:
        return result.returncode
    if any(
        int(suite.get("skipped", "0")) for suite in ET.parse(report).iter("testsuite")
    ):
        raise SystemExit("Real integration suite must not silently skip tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
