"""Resource guards must reject overrides before any Docker/container operation."""

import os
import unittest
from unittest.mock import patch

import live004_environment as environment


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
        }
        for key, value in overrides.items():
            for candidate in (value, ""):
                with self.subTest(key=key, empty=not candidate):
                    with patch.dict(os.environ, {key: candidate}, clear=True):
                        with patch.object(environment, "run") as run:
                            with self.assertRaisesRegex(SystemExit, "Refusing inherited"):
                                environment.main()
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
                            environment.main()
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


if __name__ == "__main__":
    unittest.main()
