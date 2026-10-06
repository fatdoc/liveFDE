"""PR/feature branch task ownership, fail closed for unregistered tasks."""

import os
import re
import subprocess
import sys

from repository import SCOPES


def task_for_branch(branch):
    if branch == "main":
        return None
    match = re.search(r"(?:^|/)(LIVE-\d+[A-Z]*(?:-[A-Z]+)*)(?=-|$)", branch)
    if not match or match.group(1) not in SCOPES:
        raise ValueError("Feature/PR branch must contain a registered LIVE task ID")
    return match.group(1)


def main():
    branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME", "")
    base = os.environ.get("POLICY_BASE_SHA", "")
    try:
        task = task_for_branch(branch)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    args = [sys.executable, "scripts/checks/repository.py"]
    if task:
        if not re.fullmatch(r"[0-9a-f]{40}", base) or set(base) == {"0"}:
            base = subprocess.check_output(
                ["git", "merge-base", "HEAD", "origin/main"], text=True
            ).strip()
        args += ["--task", task, "--base", base]
    # main is serial integration: structure only; feature/PR has owner checks.
    return subprocess.call(args)


if __name__ == "__main__":
    raise SystemExit(main())
