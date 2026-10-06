"""Index/tree policy + task diff scope. Run before commit; both rename sides checked."""

import argparse
import pathlib
import re
import subprocess

ROOTS = {".github", "frontend", "services", "infra", "scripts", "docs", "project-team", "config"}
FILES = {
    "LICENSE",
    ".gitignore",
    ".env.example",
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
CAPTURE_SCOPE = [
    "services/backend/src/live_review/integrations/capture/",
    "services/backend/src/live_review/modules/capture/",
    "services/backend/src/live_review/modules/materials/",
    "services/backend/src/live_review/main.py",
    "services/backend/src/live_review/core/config.py",
    "services/backend/src/live_review/workers/handlers.py",
    "services/backend/src/live_review/workers/capture_jobs.py",
    "services/backend/src/live_review/workers/capture_helper.py",
    "services/backend/src/live_review/workers/capture_operator.py",
    "services/backend/tests/test_capture.py",
    "services/backend/tests/test_capture_api.py",
    "services/backend/tests/test_capture_recording.py",
    "services/backend/tests/test_capture_providers.py",
    "services/backend/tests/test_capture_import.py",
    "services/backend/tests/capture_fixture.py",
    "services/backend/tests/capture/",
    "services/backend/pyproject.toml",
    "services/backend/uv.lock",
    "services/backend/migrations/env.py",
    "services/backend/migrations/versions/0006_capture.py",
    "config/capture.example.yaml",
    "config/capture-policy.example.yaml",
    "infra/compose.live015.yml",
    "scripts/checks/live015_environment.py",
    "scripts/checks/live015_acceptance.py",
    "scripts/checks/test_live015_environment.py",
    "docs/capture.md",
    "project-team/reports/LIVE-015/",
    "project-team/reports/LIVE-016/",
    "project-team/reports/LIVE-017/",
]
CAPTURE_UI_BACKEND_SCOPE = [
    "services/backend/src/live_review/integrations/capture/",
    "services/backend/src/live_review/modules/capture/",
    "services/backend/src/live_review/workers/capture_jobs.py",
    "services/backend/src/live_review/workers/capture_helper.py",
    "services/backend/src/live_review/workers/capture_operator.py",
    "services/backend/src/live_review/workers/capture_executor.py",
    "services/backend/src/live_review/workers/handlers.py",
    "services/backend/src/live_review/workers/dispatcher.py",
    "services/backend/src/live_review/modules/jobs/execution.py",
    "services/backend/tests/test_capture_api.py",
    "services/backend/tests/test_capture_import.py",
    "services/backend/tests/test_capture_providers.py",
    "services/backend/tests/test_capture_recording.py",
    "services/backend/tests/test_capture_executor.py",
    "services/backend/tests/capture_fixture.py",
    "services/backend/tests/capture/",
    "docs/capture.md", "project-team/reports/LIVE-020/",
]
CAPTURE_UI_FRONTEND_SCOPE = [
    "frontend/web/src/", "frontend/web/tests/", "frontend/web/vite.config.mjs",
    "project-team/reports/LIVE-021/",
]
SCOPES = {
    "LIVE-028": [
        "services/backend/src/live_review/workers/handler_process.py",
        "services/backend/tests/test_asr_error_reporting.py",
        "scripts/checks/repository.py",
        "project-team/tasks/LIVE-028.md",
        "project-team/reports/LIVE-028/",
        "project-team/STATUS.md",
        "docs/llm-settings.md",
        "docs/contracts/openapi.json",
        "docs/contracts/implementation-status.md",
        "services/backend/src/live_review/core/config.py",
        "services/backend/src/live_review/core/model_config/",
        "services/backend/src/live_review/core/model_registry.py",
        "services/backend/src/live_review/modules/llm/",
        "services/backend/src/live_review/integrations/llm/",
        "services/backend/src/live_review/main.py",
        "services/backend/tests/test_llm_settings.py",
        "services/backend/tests/test_llm_connection.py",
        "frontend/web/src/pages/Settings.tsx",
        "frontend/web/src/features/llm/",
        "frontend/web/tests/llm-settings-browser.js",
        "frontend/web/tests/llm-settings.mjs",
    ],
    "LIVE-027": [
        "services/backend/src/live_review/workers/handler_process.py",
        "services/backend/src/live_review/workers/job_runner.py",
        "services/backend/src/live_review/integrations/asr_gateway/local_worker/protocol.py",
        "services/backend/src/live_review/integrations/asr_gateway/local_worker/server.py",
        "services/backend/tests/test_asr_error_reporting.py",
        "services/backend/tests/test_local_asr_worker.py",
        "scripts/checks/repository.py", "project-team/tasks/LIVE-027.md",
        "project-team/reports/LIVE-027/", "project-team/STATUS.md",
        "frontend/web/src/features/sessions/MaterialTranscription.tsx",
        "frontend/web/src/features/sessions/LiveSessionDetail.tsx",
        "frontend/web/src/features/sessions/transcriptionTimeline.ts",
        "frontend/web/tests/material-transcription-timeline.mjs",
        "frontend/web/tests/material-transcription-browser.js",
    ],
    "LIVE-026": [
        "scripts/checks/repository.py",
        "services/backend/src/live_review/integrations/capture/douyin_bridge.py",
        "services/backend/tests/test_capture_bridge.py",
        "docs/capture.md", "project-team/tasks/LIVE-026.md", "project-team/STATUS.md",
        "project-team/reports/LIVE-026/",
    ],
    "LIVE-025": [
        "services/backend/src/live_review/integrations/capture/douyin_bridge.py",
        "scripts/checks/repository.py",
        "services/backend/src/live_review/modules/capture/",
        "services/backend/src/live_review/integrations/capture/providers.py",
        "services/backend/src/live_review/workers/capture_jobs.py",
        "services/backend/tests/test_capture_settings.py",
        "services/backend/tests/test_capture_api.py",
        "services/backend/tests/test_capture_bridge.py",
        "services/backend/tests/test_capture_providers.py",
        "services/backend/tests/capture/",
        "frontend/web/src/pages/Settings.tsx", "frontend/web/src/features/capture/",
        "frontend/web/tests/platform-settings-browser.js",
        "frontend/web/tests/platform-settings-errors.test.mjs",
        "docs/contracts/", "docs/capture.md",
        "project-team/tasks/LIVE-025.md", "project-team/reports/LIVE-025/",
        "project-team/STATUS.md", "project-team/access/RESOURCE-LOCKS.md",
    ],
    "LIVE-024": [
        "scripts/checks/repository.py",
        "services/backend/src/live_review/integrations/capture/douyin_bridge.py",
        "services/backend/src/live_review/integrations/capture/providers.py",
        "services/backend/tests/test_capture_bridge.py",
        "services/backend/tests/test_capture_providers.py",
        "project-team/tasks/LIVE-024.md",
        "project-team/STATUS.md",
        "project-team/access/RESOURCE-LOCKS.md",
        "project-team/reports/LIVE-024/",
    ],
    "LIVE-023": [
        'services/backend/src/live_review/integrations/capture/relay.py',
        'services/backend/src/live_review/integrations/capture/recording.py',
        'services/backend/src/live_review/integrations/capture/policy.py',
        'services/backend/src/live_review/integrations/capture/resolver.py',
        'services/backend/tests/test_capture_resolution.py',
        'services/backend/tests/test_capture_recording.py',
        "scripts/checks/repository.py",
        "services/backend/src/live_review/modules/capture/",
        "services/backend/src/live_review/integrations/capture/providers.py",
        "services/backend/tests/test_capture_readiness.py",
        "services/backend/tests/test_capture_executor.py",
        "frontend/web/src/features/capture/",
        "frontend/web/tests/capture-browser-contract.js",
        "project-team/tasks/LIVE-023.md",
        "project-team/STATUS.md",
        "project-team/access/RESOURCE-LOCKS.md",
        "project-team/reports/LIVE-023/",
        "docs/capture.md",
        "docs/contracts/",
    ],
    "LIVE-020": CAPTURE_UI_BACKEND_SCOPE,
    "LIVE-021": CAPTURE_UI_FRONTEND_SCOPE,
    # ARC performs reviewed serial integration of separately owned implementations.
    "LIVE-022": CAPTURE_UI_BACKEND_SCOPE + CAPTURE_UI_FRONTEND_SCOPE + [
        "scripts/checks/repository.py", "scripts/checks/live020_environment.py",
        "scripts/checks/live020_acceptance.py", "scripts/checks/live020_smoke.py",
        "scripts/checks/test_live020_environment.py", "docs/operations/live020.md",
        "docs/contracts/", "docs/README.md", "project-team/STATUS.md",
        "project-team/access/RESOURCE-LOCKS.md", "project-team/windows.md",
        "project-team/tasks/LIVE-020.md", "project-team/tasks/LIVE-021.md",
        "project-team/tasks/LIVE-022.md", "project-team/reports/LIVE-022/",
    ],
    "LIVE-019": [
        "services/backend/tests/test_local_asr_worker.py",
        ".github/workflows/checks.yml",
        "scripts/checks/",
        "docs/operations/github-ci.md",
        "project-team/tasks/LIVE-019.md",
        "project-team/reports/LIVE-019/",
    ],
    # One-time import of the existing product history into the user-owned remote.
    "LIVE-018": sorted(FILES | {root + "/" for root in ROOTS}),
    "LIVE-015": CAPTURE_SCOPE,
    "LIVE-016": CAPTURE_SCOPE,
    "LIVE-017": CAPTURE_SCOPE,
    "LIVE-006C-LOCAL": [
        "services/backend/src/live_review/integrations/asr_gateway/local/",
        "services/backend/tests/test_asr_local.py",
        "docs/asr-local.md",
        "project-team/reports/LIVE-006C/local.md",
    ],
    "LIVE-006C-TENCENT": [
        "services/backend/src/live_review/integrations/asr_gateway/tencent/",
        "services/backend/tests/test_asr_tencent.py",
        "docs/asr-tencent.md",
        "project-team/reports/LIVE-006C/tencent.md",
    ],
    "LIVE-006C-UI": [
        "frontend/web/",
        "docs/asr-ui.md",
        "project-team/reports/LIVE-006C/frontend-author.md",
    ],
    "LIVE-006C-WS": [
        "services/backend/src/live_review/modules/asr/stream.py",
        "services/backend/tests/test_asr_stream.py",
        "project-team/reports/LIVE-006C/stream.md",
    ],
    "LIVE-006C": [
        "services/backend/",
        "scripts/checks/",
        "infra/compose.live006c.yml",
        "config/asr.example.yaml",
        "config/asr-policy.example.yaml",
        "docs/",
        "project-team/",
    ],
    "LIVE-006B-CFG": [
        "services/backend/src/live_review/core/model_config/",
        "services/backend/src/live_review/core/model_registry.py",
        "services/backend/tests/test_model_config.py",
        "services/backend/tests/test_model_registry.py",
        "config/",
        ".env.example",
        "docs/ai/model-registry.md",
        "project-team/reports/LIVE-006B/config.md",
    ],
    "LIVE-006B-JOBS": [
        "services/backend/src/live_review/workers/media_jobs.py",
        "services/backend/src/live_review/workers/media_operator.py",
        "services/backend/src/live_review/workers/media_configuration.py",
        "services/backend/src/live_review/integrations/asr/factory.py",
        "services/backend/src/live_review/integrations/asr/__init__.py",
        "services/backend/tests/test_media_jobs.py",
        "services/backend/tests/test_media_registry_jobs.py",
        "docs/ai/media-jobs.md",
        "project-team/reports/LIVE-006B/jobs.md",
    ],
    "LIVE-006B": [
        ".gitignore",
        "scripts/checks/repository.py",
        "scripts/checks/test_repository.py",
        "scripts/checks/live006b_environment.py",
        "scripts/checks/live006b_acceptance.py",
        "scripts/checks/test_live006b_environment.py",
        "infra/compose.live006b.yml",
        "docs/04-directory-contract.md",
        "docs/ai/configuration-refactor.md",
        "docs/ai/provider-configuration.md",
        "docs/ai/live006-acceptance.md",
        "project-team/STATUS.md",
        "project-team/access/RESOURCE-LOCKS.md",
        "project-team/tasks/LIVE-006B.md",
        "project-team/reports/LIVE-006B/",
    ],
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
    if name.startswith("config/") and (
        path.name in {"local.yaml", "local.yml"}
        or path.name.endswith((".local.yaml", ".local.yml"))
    ):
        errors.append("private local model override")
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
