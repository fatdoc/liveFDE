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
        self.assertFalse(
            path_errors("services/backend/src/live_review/modules/models.py")
        )

    def test_rename_checks_source_and_destination(self):
        self.assertEqual(
            list(diff_paths(b"R100\0frontend/web/a.ts\0services/backend/a.ts\0")),
            ["frontend/web/a.ts", "services/backend/a.ts"],
        )


if __name__ == "__main__":
    unittest.main()
