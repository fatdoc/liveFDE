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
        "project-team/tasks/LIVE-004C.md",
        "project-team/reports/LIVE-004C/",
    ],
    "LIVE-004": [
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
