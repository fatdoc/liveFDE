"""A wrong broker must be rejected before pytest can consume or ACK messages."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import backend_integration_tests as runner


class BrokerGuardTests(unittest.TestCase):
    def invoke(self, broker, *, ci=False):
        root = Path(runner.__file__).resolve().parents[2]
        workspace = root.parent.parent if root.parent.name == ".worktrees" else root.parent
        role, port = ("live002", 15432) if ci else ("live005_qa", 15450)
        path = workspace / "runtime" / ("live-002/private.env" if ci else "live-005/qa.env")
        content = f"LIVE_DATABASE_URL=postgresql+psycopg://{role}:fixture@127.0.0.1:{port}/{role}\n"
        content += "LIVE_BROKER_URL=" + broker + "\n"
        with (
            patch.dict(os.environ, {"GITHUB_ACTIONS": "true"} if ci else {}, clear=True),
            patch.object(sys, "argv", ["runner", "--env-file", str(path)]),
            patch.object(Path, "read_text", return_value=content),
            patch.object(Path, "stat", return_value=SimpleNamespace(st_mode=0o100600)),
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(
                runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ) as run,
            patch.object(
                runner.ET,
                "parse",
                return_value=runner.ET.fromstring(
                    '<testsuites><testsuite tests="1" skipped="0"/></testsuites>'
                ),
            ),
        ):
            try:
                result = runner.main()
            except SystemExit:
                run.assert_not_called()
                raise
            run.assert_called_once()
            return result

    def test_wrong_broker_rejected_before_pytest(self):
        good = "amqp://live005_qa:fixture@127.0.0.1:5675/live005_qa"
        bad = [
            good.replace("127.0.0.1", "remote.invalid"),
            good.replace(":5675", ":5672"),
            good.replace("//live005_qa:", "//foreign:"),
            good.rsplit("/", 1)[0] + "/live005_be",
            good + "?override=1",
            good + "#fragment",
            good.replace("amqp:", "redis:"),
        ]
        for broker in bad:
            with self.subTest(broker=broker), self.assertRaises(SystemExit):
                self.invoke(broker)

    def test_registered_local_and_ci_destinations_accepted(self):
        self.assertEqual(self.invoke("amqp://live005_qa:fixture@127.0.0.1:5675/live005_qa"), 0)
        self.assertEqual(self.invoke("amqp://live002:fixture@127.0.0.1:5673//", ci=True), 0)


if __name__ == "__main__":
    unittest.main()
