import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import live015_environment as environment


class EnvironmentTests(unittest.TestCase):
    def write_config(self, runtime):
        values = {
            "LIVE_DATABASE_URL": "postgresql+psycopg://live015:"
            + "a" * 48
            + "@127.0.0.1:15490/live015",
            "LIVE_BROKER_URL": "amqp://unconfigured:unconfigured@127.0.0.1:1//",
            "LIVE_STORAGE_ROOT": str(runtime / "storage"),
            "LIVE_MODEL_CONFIG_DIR": str(runtime / "config"),
        }
        path = runtime / "private.env"
        path.write_text("\n".join(k + "=" + v for k, v in values.items()))
        path.chmod(0o600)
        return path

    def test_private_config_and_environment_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp).resolve()
            self.write_config(runtime)
            with (
                patch.object(environment, "RUNTIME", runtime),
                patch.dict(
                    os.environ,
                    {
                        "LIVE_TEST_DATABASE_URL": "foreign",
                        "LIVE_CAPTURE_DOUYIN_COOKIE": "synthetic-only",
                    },
                    clear=True,
                ),
            ):
                env = environment.environment()
                self.assertNotIn("LIVE_TEST_DATABASE_URL", env)
                self.assertEqual(env["LIVE_CAPTURE_DOUYIN_COOKIE"], "synthetic-only")

    def test_foreign_port_and_duplicate_key_rejected(self):
        for kind in ("port", "duplicate"):
            with tempfile.TemporaryDirectory() as temp:
                runtime = Path(temp).resolve()
                path = self.write_config(runtime)
                content = path.read_text()
                path.write_text(
                    content.replace("15490", "15480")
                    if kind == "port"
                    else content + "\n" + content.splitlines()[0]
                )
                with patch.object(environment, "RUNTIME", runtime):
                    with self.assertRaises(RuntimeError):
                        environment.environment()

    def test_fifo_symlink_permissions_and_size_rejected(self):
        for kind in ("fifo", "symlink", "permissions", "oversize"):
            with tempfile.TemporaryDirectory() as temp:
                runtime = Path(temp).resolve()
                path = runtime / "private.env"
                if kind == "fifo":
                    os.mkfifo(path, 0o600)
                elif kind == "symlink":
                    path.symlink_to(runtime / "missing")
                else:
                    self.write_config(runtime)
                    if kind == "permissions":
                        path.chmod(0o644)
                    else:
                        path.write_text("x" * 8193)
                with patch.object(environment, "RUNTIME", runtime):
                    with self.assertRaises((RuntimeError, OSError)):
                        environment.environment()
