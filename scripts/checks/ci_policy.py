"""PR/feature branch task ownership, fail closed for unregistered tasks."""

import os
import re
import subprocess
import sys

from repository import SCOPES

branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME", "")
base = os.environ.get("POLICY_BASE_SHA", "")
match = re.search(r"(?:^|/)(?:LIVE-\d+)", branch)
args = [sys.executable, "scripts/checks/repository.py"]
if branch != "main":
    if not match:
        raise SystemExit("Feature/PR branch must contain a registered LIVE task ID")
    task = match.group().lstrip("/")
    if task not in SCOPES:
        raise SystemExit("Task ownership must be registered before CI can approve it")
    if not re.fullmatch(r"[0-9a-f]{40}", base) or set(base) == {"0"}:
        base = subprocess.check_output(
            ["git", "merge-base", "HEAD", "origin/main"], text=True
        ).strip()
    args += ["--task", task, "--base", base]
# main is a serial integration ref: structure only, task checks ran on feature/PR.
raise SystemExit(subprocess.call(args))
