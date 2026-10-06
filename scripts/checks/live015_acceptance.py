"""Isolated zero-skip suite. Every run gets a fresh LIVE-015 database and evidence folder."""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from uuid import uuid4

from live015_environment import ROOT, RUNTIME, environment
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    env = environment()
    name = "live015_suite_" + uuid4().hex
    engine = create_engine(env["LIVE_DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        assert conn.execute(text("select current_database(),current_user")).one() == (
            "live015",
            "live015",
        )
        conn.execute(text(f'CREATE DATABASE "{name}" OWNER live015'))
        conn.execute(text(f'ALTER DATABASE "{name}" SET timezone TO \'UTC\''))
    engine.dispose()
    env["LIVE_DATABASE_URL"] = (
        make_url(env["LIVE_DATABASE_URL"])
        .set(database=name)
        .render_as_string(hide_password=False)
    )
    env["LIVE_TEST_DATABASE_URL"] = env["LIVE_DATABASE_URL"]
    evidence = RUNTIME / "evidence" / name
    evidence.mkdir()
    report = evidence / "pytest.xml"
    selected = (
        ["tests", "--ignore=tests/test_jobs_broker.py"]
        if args.all
        else [
            "tests/test_capture_api.py",
            "tests/test_capture_import.py",
            "tests/test_capture_recording.py",
            "tests/test_capture_providers.py",
        ]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *selected,
            "-q",
            f"--junitxml={report}",
            f"--basetemp={evidence / 'tmp'}",
        ],
        env=env,
        cwd=ROOT / "services/backend",
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    (evidence / "pytest.log").write_text(result.stdout + result.stderr)
    counts = {key: 0 for key in ("tests", "errors", "failures", "skipped")}
    if report.exists():
        for suite in ET.parse(report).iter("testsuite"):
            for key in counts:
                counts[key] += int(suite.get(key, "0"))
    print(
        json.dumps(
            {
                "returncode": result.returncode,
                "counts": counts,
                "evidence": str(evidence),
            }
        )
    )
    if result.returncode:
        print(result.stdout[-20000:])
    raise SystemExit(result.returncode or bool(counts["skipped"]))


if __name__ == "__main__":
    main()
