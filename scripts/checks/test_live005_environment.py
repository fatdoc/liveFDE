"""Resource guards must reject overrides before any Docker/container operation."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import live005_environment as environment


class ResourceBoundaryTests(unittest.TestCase):
    def test_inherited_overrides_fail_before_any_docker_call(self):
        overrides = {
            "LIVE_RUNTIME": "/outside/workspace",
            "PG_PASSWORD": "foreign-secret",
            "COMPOSE_FILE": "/outside/compose.yaml",
            "COMPOSE_PROJECT_NAME": "foreign-project",
            "COMPOSE_ENV_FILES": "/outside/private.env",
            "COMPOSE_PROFILES": "foreign",
            "DOCKER_HOST": "tcp://remote.invalid:2375",
            "DOCKER_CONTEXT": "foreign-context",
            "DOCKER_CONFIG": "/outside/docker",
            "DOCKER_TLS_VERIFY": "1",
            "RABBITMQ_NODENAME": "foreign@localhost",
            "ERL_FLAGS": "foreign",
            "MQ_COOKIE": "foreign",
        }
        for key, value in overrides.items():
            for candidate in (value, ""):
                with self.subTest(key=key, empty=not candidate):
                    with patch.dict(os.environ, {key: candidate}, clear=True):
                        with patch.object(environment, "run") as run:
                            with self.assertRaisesRegex(SystemExit, "Refusing inherited"):
                                environment.main([])
                            run.assert_not_called()

    def test_remote_context_never_reaches_container_operations(self):
        for endpoint in (
            "tcp://remote:2375",
            "ssh://remote",
            "unix://remote/socket",
            "unix:///socket?override=true",
            "unix:relative",
        ):
            with self.subTest(endpoint=endpoint):
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(environment, "run", return_value=endpoint) as run:
                        with self.assertRaisesRegex(SystemExit, "non-local"):
                            environment.main([])
                        self.assertEqual(run.call_count, 1)
                        self.assertEqual(run.call_args.args[0][1:3], ["context", "inspect"])

    def test_local_endpoint_is_pinned_in_explicit_child_environment(self):
        with patch.dict(os.environ, {"PATH": "/bin"}, clear=True):
            with patch.object(environment, "run", return_value="unix:///local/docker.sock\n"):
                child = environment.safe_parent_environment()
        self.assertEqual(child, {"PATH": "/bin", "DOCKER_HOST": "unix:///local/docker.sock"})
        with patch.object(environment.subprocess, "run") as runner:
            environment.run(["docker", "ps"], env=child)
            self.assertEqual(runner.call_args.kwargs["env"], child)


class RabbitBoundaryTests(unittest.TestCase):
    def test_foreign_pid_never_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "rabbit.pid").write_text("12345")
            with patch.object(environment, "MQ_BASE", base):
                with (
                    patch.object(
                        environment.subprocess,
                        "run",
                        return_value=SimpleNamespace(
                            returncode=0,
                            stdout="beam.smp -sname foreign@localhost -mnesia /outside",
                        ),
                    ),
                    patch.object(environment, "run") as run,
                ):
                    with self.assertRaisesRegex(SystemExit, "foreign MQ"):
                        environment.mq_stop({}, {})
                    run.assert_not_called()

    def test_task_env_rejects_other_vhost_or_db(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            values = {
                "LIVE_DATABASE_URL": "postgresql+psycopg://live005_be:"
                + "a" * 48
                + "@127.0.0.1:15450/live005_be",
                "LIVE_BROKER_URL": "amqp://live005_be:" + "b" * 48 + "@127.0.0.1:5675/live005_be",
                "LIVE_STORAGE_ROOT": str(base / "storage-be"),
                "LIVE_TASK_QUEUE": "live005_be",
            }
            with patch.object(environment, "RUNTIME", base):
                for field, value in [
                    (
                        "LIVE_BROKER_URL",
                        values["LIVE_BROKER_URL"].replace("/live005_be", "/live005_qa"),
                    ),
                    (
                        "LIVE_DATABASE_URL",
                        values["LIVE_DATABASE_URL"].replace("15450", "5432"),
                    ),
                ]:
                    with patch.object(
                        environment,
                        "read_private",
                        return_value=values | {field: value},
                    ):
                        with self.assertRaisesRegex(SystemExit, "changed task"):
                            environment.validate_task_env("be")

    def test_stopped_mq_never_issues_stop(self):
        with (
            patch.object(environment, "owned_mq_pid", return_value=None),
            patch.object(environment, "run") as run,
        ):
            environment.mq_stop({}, {})
            run.assert_not_called()

    def test_private_env_rejects_symlink_and_readable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "target"
            target.write_text("KEY=value")
            link = base / "link"
            link.symlink_to(target)
            for candidate in (target, link):
                with self.assertRaisesRegex(SystemExit, "mode 600"):
                    environment.read_private(candidate)


if __name__ == "__main__":
    unittest.main()
