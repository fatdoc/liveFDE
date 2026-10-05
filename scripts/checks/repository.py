"""Index/tree policy + task diff scope. Run before commit; both rename sides checked."""

import argparse
import pathlib
import re
import subprocess

ROOTS = {".github", "frontend", "services", "infra", "scripts", "docs", "project-team"}
FILES = {
    ".gitignore",
    ".dockerignore",
    "AGENTS.md",
    "README.md",
    "PRODUCT.md",
    "TASK.md",
    "package.json",
}
BAD_PARTS = {
    "node_modules",
    ".venv",
    "__pycache__",
    "runtime",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    "model-weights",
}
BAD_SUFFIX = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".log",
    ".pid",
    ".db",
    ".mp4",
    ".mp3",
    ".wav",
    ".webm",
    ".onnx",
}
SCOPES = {
    "LIVE-006-CFG": [
        "services/backend/src/live_review/core/provider_config.py",
        "services/backend/pyproject.toml",
        "services/backend/uv.lock",
        "services/backend/tests/test_provider_config.py",
        "infra/providers.example.yaml",
        "infra/providers.offline.example.yaml",
        "docs/ai/provider-configuration.md",
        "project-team/reports/LIVE-006/config.md",
    ],
    "LIVE-006": [
        "services/backend/src/live_review/integrations/media/",
        "services/backend/src/live_review/integrations/asr/",
        "services/backend/tests/test_media.py",
        "services/backend/tests/test_asr.py",
        "services/backend/tests/test_asr_transport.py",
        "services/backend/tests/fixtures/",
        "docs/ai/media-asr.md",
        "project-team/tasks/LIVE-006.md",
        "project-team/reports/LIVE-006/change.md",
    ],
    "LIVE-006-JOBS": [
        "services/backend/src/live_review/workers/handlers.py",
        "services/backend/src/live_review/workers/media_jobs.py",
        "services/backend/src/live_review/workers/media_artifacts.py",
        "services/backend/src/live_review/workers/media_operator.py",
        "services/backend/src/live_review/workers/media_calls.py",
        "services/backend/tests/test_media_jobs.py",
        "docs/ai/media-jobs.md",
    ],
    "LIVE-006-ARC": [
        "services/backend/src/live_review/workers/handlers.py",
        "services/backend/src/live_review/workers/media_jobs.py",
        "services/backend/tests/test_media_jobs.py",
        "infra/compose.live006.yml",
        "scripts/checks/live006_environment.py",
        "scripts/checks/live006_smoke.py",
        "scripts/checks/test_live006_environment.py",
        "scripts/checks/repository.py",
        "docs/ai/banana-reference.md",
        "docs/ai/live006-acceptance.md",
        "docs/contracts/implementation-status.md",
        "project-team/STATUS.md",
        "project-team/access/RESOURCE-LOCKS.md",
        "project-team/tasks/LIVE-006.md",
        "project-team/reports/LIVE-006/",
    ],
    "LIVE-005": [
        "services/backend/src/live_review/modules/jobs/",
        "services/backend/src/live_review/workers/",
        "services/backend/migrations/versions/0004_jobs.py",
        "services/backend/tests/test_jobs.py",
        "services/backend/tests/test_jobs_recovery.py",
        "services/backend/tests/test_jobs_broker.py",
        "services/backend/tests/jobs_fixture.py",
        "project-team/tasks/LIVE-005.md",
        "project-team/reports/LIVE-005/change.md",
    ],
    "LIVE-005-ENG": [
        "infra/compose.live005.yml",
        "scripts/checks/live005_environment.py",
        "scripts/checks/test_live005_environment.py",
        "docs/operations/live-005.md",
        "project-team/reports/LIVE-005/environment.md",
    ],
    "LIVE-005-ARC": [
        "services/backend/src/live_review/core/config.py",
        "services/backend/src/live_review/main.py",
        "services/backend/migrations/env.py",
        "services/backend/tests/test_job_config.py",
        "scripts/checks/repository.py",
        "scripts/checks/backend_integration_tests.py",
        "scripts/checks/test_backend_integration_tests.py",
        "scripts/checks/live005_smoke.py",
        "scripts/checks/live005_scenarios.py",
        "docs/contracts/",
        "docs/operations/backend-foundation.md",
        "project-team/STATUS.md",
        "project-team/tasks/LIVE-005.md",
        "project-team/access/RESOURCE-LOCKS.md",
        "project-team/reports/LIVE-005/",
    ],
    "LIVE-004A": [
        "services/backend/src/live_review/core/",
        "services/backend/src/live_review/modules/identity/",
        "services/backend/src/live_review/modules/__init__.py",
        "services/backend/src/live_review/main.py",
        "services/backend/pyproject.toml",
        "services/backend/uv.lock",
        "services/backend/migrations/env.py",
        "services/backend/migrations/versions/0001_identity.py",
        "services/backend/tests/test_identity.py",
        "services/backend/tests/conftest.py",
        "project-team/tasks/LIVE-004A.md",
        "project-team/reports/LIVE-004A/",
    ],
    "LIVE-004B": [
        "services/backend/src/live_review/modules/streamers/",
        "services/backend/src/live_review/modules/sessions/",
        "services/backend/src/live_review/main.py",
        "services/backend/migrations/env.py",
        "services/backend/migrations/versions/0002_sessions.py",
        "services/backend/tests/test_sessions.py",
        "project-team/tasks/LIVE-004B.md",
        "project-team/reports/LIVE-004B/",
    ],
    "LIVE-004C": [
        "services/backend/src/live_review/modules/materials/",
        "services/backend/src/live_review/integrations/storage/",
        "services/backend/migrations/versions/0003_materials.py",
        "services/backend/tests/test_materials.py",
        "services/backend/tests/materials_fixture.py",
        "project-team/tasks/LIVE-004C.md",
        "project-team/reports/LIVE-004C/",
    ],
    "LIVE-004": [
        ".github/workflows/checks.yml",
        "scripts/checks/",
        "infra/",
        "docs/contracts/",
        "docs/operations/",
        "services/backend/src/live_review/main.py",
        "services/backend/migrations/env.py",
        "project-team/tasks/LIVE-004.md",
        "project-team/STATUS.md",
        "project-team/access/RESOURCE-LOCKS.md",
        "project-team/reports/LIVE-004/",
    ],
    "LIVE-004-ENG": [
        "scripts/checks/repository.py",
        "scripts/checks/ci_policy.py",
        "scripts/checks/test_repository.py",
        "scripts/checks/live004_environment.py",
        "scripts/checks/test_live004_environment.py",
        "infra/compose.live004.yml",
        "docs/operations/live-004.md",
        "project-team/reports/LIVE-004/engineering.md",
    ],
    "LIVE-002": [
        "services/backend/",
        "infra/",
        "scripts/checks/",
        ".github/workflows/",
        "docs/operations/",
        "project-team/tasks/LIVE-002.md",
        "project-team/reports/LIVE-002/",
    ],
    "LIVE-003": [
        "docs/contracts/",
        "docs/07-integration-plan.md",
        "docs/13-window-collaboration.md",
        "project-team/tasks/LIVE-003.md",
        "project-team/reports/LIVE-003/",
    ],
}


def git(*args):
    return subprocess.check_output(["git", *args])


def path_errors(name):
    path = pathlib.PurePosixPath(name)
    errors = []
    if path.parts[0] not in ROOTS and name not in FILES:
        errors.append("unknown root")
    if (
        any(part in BAD_PARTS for part in path.parts)
        or path.suffix in BAD_SUFFIX
        or ".sqlite" in name
    ):
        errors.append("runtime/binary/credential artifact")
    if any(part.startswith(".env") and not part.endswith(".example") for part in path.parts):
        errors.append("private environment")
    if name.startswith("services/") and not name.startswith("services/backend/"):
        errors.append("unknown service")
    if name.startswith("frontend/") and not name.startswith("frontend/web/"):
        errors.append("unknown frontend")
    return errors


def diff_paths(raw):
    items = iter(raw.decode().split("\0"))
    for status in items:
        if not status:
            continue
        yield next(items)
        if status.startswith(("R", "C")):
            yield next(items)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--task", choices=SCOPES)
    args = parser.parse_args()
    errors = []
    for name in git("ls-files", "-z").decode().split("\0"):
        if not name:
            continue
        errors.extend(f"{name}: {e}" for e in path_errors(name))
        data = git("show", f":{name}")
        if re.search(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----", data):
            errors.append(f"{name}: private key content")
        if re.search(rb"(?:sk-[A-Za-z0-9]{24,}|AKIA[A-Z0-9]{16})", data):
            errors.append(f"{name}: credential pattern")
    if args.task:
        diff = ["diff", "--name-status", "-z", "--find-renames"]
        diff += [args.base, "HEAD"] if args.base else ["--cached"]
        for name in diff_paths(git(*diff)):
            if not any(
                name.startswith(p) if p.endswith("/") else name == p for p in SCOPES[args.task]
            ):
                errors.append(f"{name}: outside {args.task} ownership (including rename source)")
    for error in errors:
        print(error)
    print(f"Repository policy: {len(errors)} violation(s)")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
