"""006 resource guard tests; no Docker mutation or real secrets."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import live006_environment as env
import live006_smoke as smoke


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


class SmokeEnvironmentTests(unittest.TestCase):
    def test_inherited_config_and_extra_private_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve()
            path = runtime / "private.env"
            password = "a" * 48
            payload = (
                f"LIVE_RUNTIME={runtime}\nPG_PASSWORD={password}\n"
                f"LIVE_DATABASE_URL=postgresql+psycopg://live006:{password}@127.0.0.1:15460/live006\n"
                "LIVE_BROKER_URL=amqp://unconfigured:unconfigured@127.0.0.1:1//\n"
                f"LIVE_STORAGE_ROOT={runtime / 'storage'}\n"
            )
            path.write_text(payload)
            path.chmod(0o600)
            with (
                patch.object(smoke, "RUNTIME", runtime),
                patch.dict(
                    os.environ,
                    {"LIVE_LOGIN_LIMIT": "0", "LIVE_DATABASE_URL": "foreign"},
                    clear=True,
                ),
            ):
                result = smoke.environment()
                self.assertNotIn("LIVE_LOGIN_LIMIT", result)
                self.assertIn("15460/live006", result["LIVE_DATABASE_URL"])
                for extra in ("LIVE_LOGIN_LIMIT=0\n", "PG_PASSWORD=duplicate\n"):
                    path.write_text(payload + extra)
                    with self.assertRaisesRegex(RuntimeError, "invalid_private"):
                        smoke.environment()

    def test_fifo_or_oversize_smoke_environment_rejected(self):
        for kind in ("fifo", "large"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                runtime = Path(directory).resolve()
                path = runtime / "private.env"
                if kind == "fifo":
                    os.mkfifo(path, 0o600)
                else:
                    path.write_text("x" * 8193)
                    path.chmod(0o600)
                with patch.object(smoke, "RUNTIME", runtime):
                    with self.assertRaisesRegex(RuntimeError, "unsafe_private"):
                        smoke.environment()


if __name__ == "__main__":
    unittest.main()
