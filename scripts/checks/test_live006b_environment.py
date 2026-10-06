"""006 resource guard tests; no Docker mutation or real secrets."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import live006b_acceptance as acceptance
import live006b_environment as env


class EnvironmentTests(unittest.TestCase):
    def test_overrides_rejected_before_docker(self):
        for key in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "COMPOSE_FILE",
            "PG_PASSWORD",
            "LIVE_RUNTIME",
        ):
            with self.subTest(key=key), patch.dict(os.environ, {key: ""}, clear=True):
                with patch.object(env.subprocess, "check_output") as run:
                    with self.assertRaisesRegex(SystemExit, "inherited"):
                        env.main()
                    run.assert_not_called()

    def test_nonlocal_context_rejected_before_container_call(self):
        for endpoint in (
            "tcp://remote:2375",
            "ssh://remote",
            "unix://remote/socket",
            "unix:relative",
        ):
            with (
                self.subTest(endpoint=endpoint),
                patch.dict(os.environ, {}, clear=True),
            ):
                with patch.object(env.subprocess, "check_output", return_value=endpoint) as run:
                    with self.assertRaisesRegex(SystemExit, "nonlocal"):
                        env.main()
                    self.assertEqual(run.call_count, 1)

    def test_redirected_checkout_rejected(self):
        with patch.object(env, "ROOT", Path("/foreign/app")):
            with patch.object(env.subprocess, "check_output") as run:
                with self.assertRaisesRegex(SystemExit, "checkout"):
                    env.main()
                run.assert_not_called()

    def test_unsafe_private_env_never_reaches_container(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve()
            path = runtime / "private.env"
            path.write_text("PG_PASSWORD=not-a-real-key\n")
            path.chmod(0o644)
            with (
                patch.object(env, "RUNTIME", runtime),
                patch.dict(os.environ, {}, clear=True),
            ):
                with patch.object(
                    env.subprocess, "check_output", return_value="unix:///local"
                ) as run:
                    with self.assertRaisesRegex(SystemExit, "unsafe credentials"):
                        env.main()
                    self.assertEqual(run.call_count, 1)

    def test_fifo_and_large_private_env_rejected(self):
        for kind in ("fifo", "large"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                runtime = Path(directory).resolve()
                path = runtime / "private.env"
                if kind == "fifo":
                    os.mkfifo(path, 0o600)
                else:
                    path.write_text("x" * 8193)
                    path.chmod(0o600)
                with (
                    patch.object(env, "RUNTIME", runtime),
                    patch.dict(os.environ, {}, clear=True),
                ):
                    with patch.object(
                        env.subprocess, "check_output", return_value="unix:///local"
                    ) as run:
                        with self.assertRaisesRegex(SystemExit, "unsafe credentials"):
                            env.main()
                        self.assertEqual(run.call_count, 1)

    def test_foreign_destination_never_reaches_container(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve()
            path = runtime / "private.env"
            path.write_text(
                "PG_PASSWORD=" + "a" * 48 + "\n"
                f"LIVE_RUNTIME={runtime}\nLIVE_STORAGE_ROOT={runtime / 'storage'}\n"
                "LIVE_DATABASE_URL=postgresql+psycopg://foreign@127.0.0.1:5432/foreign\n"
                "LIVE_BROKER_URL=amqp://unconfigured:unconfigured@127.0.0.1:1//\n"
            )
            path.chmod(0o600)
            with (
                patch.object(env, "RUNTIME", runtime),
                patch.dict(os.environ, {}, clear=True),
            ):
                with patch.object(
                    env.subprocess, "check_output", return_value="unix:///local"
                ) as run:
                    with self.assertRaisesRegex(SystemExit, "changed task"):
                        env.main()
                    self.assertEqual(run.call_count, 1)


class AcceptanceBoundaryTests(unittest.TestCase):
    def test_private_destination_and_inherited_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "private.env"
            secret = "a" * 48
            payload = (
                f"LIVE_RUNTIME={root}\nPG_PASSWORD={secret}\n"
                f"LIVE_DATABASE_URL=postgresql+psycopg://live006b:{secret}@127.0.0.1:15470/live006b\n"
                "LIVE_BROKER_URL=amqp://unconfigured:unconfigured@127.0.0.1:1//\n"
                f"LIVE_STORAGE_ROOT={root / 'storage'}\n"
            )
            path.write_text(payload)
            path.chmod(0o600)
            with (
                patch.object(acceptance, "RUNTIME", root),
                patch.dict(
                    os.environ,
                    {"LIVE_ASR_API_KEY": "synthetic-unused", "LIVE_MODEL_ASR_DEFAULT": "foreign"},
                    clear=True,
                ),
            ):
                clean = acceptance.environment()
                self.assertNotIn("LIVE_ASR_API_KEY", clean)
                self.assertNotIn("LIVE_MODEL_ASR_DEFAULT", clean)
                path.write_text(payload.replace("15470", "15460"))
                with self.assertRaisesRegex(RuntimeError, "foreign_acceptance"):
                    acceptance.environment()
                path.write_text(payload + "LIVE_ASR_API_KEY=synthetic-unused\n")
                with self.assertRaisesRegex(RuntimeError, "invalid_private"):
                    acceptance.environment()

    def test_fifo_refused_without_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            os.mkfifo(root / "private.env", 0o600)
            with patch.object(acceptance, "RUNTIME", root):
                with self.assertRaisesRegex(RuntimeError, "unsafe_private"):
                    acceptance.environment()


if __name__ == "__main__":
    unittest.main()
