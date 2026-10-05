import unittest

from ci_policy import task_for_branch
from repository import SCOPES, diff_paths, path_errors


class PolicyTests(unittest.TestCase):
    def test_task_branch_ids_are_not_truncated(self):
        for task in (
            "LIVE-002",
            "LIVE-003",
            "LIVE-004A",
            "LIVE-004B",
            "LIVE-004C",
            "LIVE-004-ENG",
            "LIVE-004",
        ):
            self.assertEqual(task_for_branch(f"feat/{task}-implementation"), task)
        for branch in (
            "feat/LIVE-004D-new",
            "feat/LIVE-004AB-new",
            "feat/LIVE-999-new",
            "feat/misc",
            "feat/LIVE-004A1-new",
            "chore/LIVE-004-UNKNOWN-new",
            "chore/LIVE-004-ENGFOO-new",
        ):
            with self.assertRaises(ValueError, msg=branch):
                task_for_branch(branch)
        self.assertIsNone(task_for_branch("main"))

    def test_business_scopes_do_not_grant_sibling_or_lock_access(self):
        def allowed(task, path):
            return any(path.startswith(p) if p.endswith("/") else path == p for p in SCOPES[task])

        prefix = "services/backend/"
        for task in ("LIVE-004B", "LIVE-004C"):
            self.assertFalse(allowed(task, prefix + "uv.lock"))
            self.assertFalse(allowed(task, prefix + "src/live_review/core/config.py"))
        self.assertFalse(allowed("LIVE-004A", prefix + "migrations/versions/0002_sessions.py"))
        self.assertFalse(
            allowed("LIVE-004B", prefix + "src/live_review/modules/materials/router.py")
        )
        self.assertFalse(allowed("LIVE-004C", prefix + "src/live_review/main.py"))
        self.assertFalse(allowed("LIVE-004-ENG", prefix + "src/live_review/main.py"))
        self.assertTrue(allowed("LIVE-004B", prefix + "migrations/versions/0002_sessions.py"))

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
