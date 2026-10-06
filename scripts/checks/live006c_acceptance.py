"""Zero-skip regression on a new database, never on existing UI or earlier-round data."""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from uuid import uuid4

from live006c_runtime import ROOT, RUNTIME, environment, new_database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-only", action="store_true")
    args = parser.parse_args()
    env = environment()
    target = new_database(env, "suite")
    directory = RUNTIME / "integration" / uuid4().hex
    directory.mkdir(parents=True)
    (directory / "target.json").write_text(
        json.dumps({"database": target, "port": 15480, "role": "live006c"})
    )
    report = directory / "pytest.xml"
    selected = (
        ["tests/test_asr_api.py", "tests/test_asr_gateway.py", "tests/test_asr_formats.py"]
        if args.gateway_only
        else ["tests", "--ignore=tests/test_jobs_broker.py"]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *selected,
            "-q",
            f"--junitxml={report}",
            f"--basetemp={directory / 'pytest-temp'}",
        ],
        cwd=ROOT / "services/backend",
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    (directory / "pytest.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        print(json.dumps({"status": "failed", "report_directory": str(directory)}))
        raise SystemExit(result.returncode)
    suites = ET.parse(report).iter("testsuite")
    counts = {key: 0 for key in ("tests", "errors", "failures", "skipped")}
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
    assert counts["skipped"] == counts["errors"] == counts["failures"] == 0
    print(json.dumps({"status": "passed", "counts": counts, "report": str(report)}))


if __name__ == "__main__":
    main()
