import unittest

from repository import diff_paths, path_errors


class PolicyTests(unittest.TestCase):
    def test_artifacts_and_secrets(self):
        for path in [
            "unknown/a.py",
            "infra/.env",
            "services/backend/runtime/a",
            "docs/movie.mp4",
            "frontend/old/a.ts",
        ]:
            self.assertTrue(path_errors(path), path)
        self.assertFalse(path_errors("infra/.env.example"))
        self.assertFalse(path_errors("services/backend/src/live_review/modules/models.py"))

    def test_rename_checks_source_and_destination(self):
        self.assertEqual(
            list(diff_paths(b"R100\0frontend/web/a.ts\0services/backend/a.ts\0")),
            ["frontend/web/a.ts", "services/backend/a.ts"],
        )


class RealRenamePolicyTest(unittest.TestCase):
    def test_cross_owner_rename_is_rejected(self):
        import pathlib
        import subprocess
        import sys
        import tempfile

        root = pathlib.Path(__file__).resolve().parents[2]
        workspace = root.parent.parent if root.parent.name == ".worktrees" else root.parent
        temporary_root = workspace / "runtime/live-002/policy-tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            checkout = pathlib.Path(directory)

            def git(*args):
                subprocess.run(["git", *args], cwd=checkout, check=True, capture_output=True)

            git("init", "-q")
            (checkout / "frontend/web").mkdir(parents=True)
            (checkout / "services/backend").mkdir(parents=True)
            (checkout / "frontend/web/example.ts").write_text("// synthetic policy fixture\n")
            git("add", "frontend/web/example.ts")
            git(
                "-c",
                "user.name=Policy Test Fixture",
                "-c",
                "user.email=fixture@invalid",
                "commit",
                "-qm",
                "synthetic policy test baseline",
            )
            git("mv", "frontend/web/example.ts", "services/backend/example.ts")
            result = subprocess.run(
                [sys.executable, str(root / "scripts/checks/repository.py"), "--task", "LIVE-002"],
                cwd=checkout,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("frontend/web/example.ts: outside LIVE-002", result.stdout)


if __name__ == "__main__":
    unittest.main()
