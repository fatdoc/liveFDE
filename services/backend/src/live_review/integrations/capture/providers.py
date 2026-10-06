"""Pinned upstreams behind process boundaries; no upstream scheduler/recorder is reused."""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from live_review.integrations.capture.contracts import CaptureError, Source

DOUYIN_COMMIT = "add187f8d8c7ff7d231fcbee45cbb4f1ed247d3a"
FINDER_VERSION = "0.4.3"
DOUYIN_ERRORS = frozenset(
    {
        "source_parse_failed",
        "provider_dependencies_missing",
        "source_auth_required",
        "source_http_error",
        "source_rate_limited",
        "source_challenge_required",
        "source_empty_response",
        "source_schema_changed",
        "source_protocol_error",
        "source_timeout",
        "source_network_error",
        "https_required",
        "unsafe_stream_url",
        "domain_not_allowed",
    }
)


def canonical_reference(platform, reference):
    if platform == "wechat" and reference == "phone_cast":
        return reference
    if platform == "douyin" and re.fullmatch(r"https://live\.douyin\.com/[0-9]{1,24}/?", reference):
        return reference.rstrip("/")
    raise CaptureError("invalid_source")


def communicate(command, tick, timeout, payload=None, cwd=None):
    """Pipes are private; upstream stdout/stderr must never reach application logs."""
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=cwd
    )
    end = time.monotonic() + timeout
    try:
        first = True
        while True:
            tick()
            try:
                output, _ = process.communicate(payload if first else None, timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                first = False
                if time.monotonic() >= end:
                    raise CaptureError("source_timeout") from None
        if process.returncode or len(output) > 65536:
            raise CaptureError("source_parse_failed")
        return output
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


class DouyinProvider:
    def __init__(self, policy, *, cookie=None):
        self.policy = policy
        # Explicit empty workspace snapshots never fall back to process-global credentials.
        self._cookie = (
            os.environ.get(policy.douyin_cookie_env, "") if cookie is None else cookie
        ).strip()

    def health(self):
        p = self.policy
        ready = bool(
            p.douyin_python
            and p.douyin_python.is_file()
            and p.douyin_checkout
            and (p.douyin_checkout / "src/spider.py").is_file()
            and shutil.which("node")
        )
        return {
            "dependencies_ready": ready,
            "real_platform_verified": False,
            "cookie_configured": bool(self._cookie),
            "upstream_commit": DOUYIN_COMMIT,
            "requires_phone": False,
        }

    def probe(self, reference, tick):
        canonical_reference("douyin", reference)
        if not self.health()["dependencies_ready"]:
            raise CaptureError("provider_dependencies_missing")
        p = self.policy
        revision = subprocess.run(
            ["git", "-C", str(p.douyin_checkout), "rev-parse", "HEAD"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        if revision.stdout.decode().strip() != DOUYIN_COMMIT:
            raise CaptureError("upstream_version_mismatch")
        payload = json.dumps(
            {
                "source": reference,
                "checkout": str(p.douyin_checkout),
                "cookie": self._cookie,
                "https_only": p.https_only,
                "stream_domains": p.stream_domains,
            }
        ).encode()
        for attempt in range(p.probe_attempts):
            try:
                output = communicate(
                    [str(p.douyin_python), str(Path(__file__).with_name("douyin_bridge.py"))],
                    tick,
                    p.probe_seconds,
                    payload,
                    p.douyin_checkout,
                )
                data = json.loads(output)
                if not isinstance(data, dict):
                    raise CaptureError("source_parse_failed")
                if data.get("error"):
                    code = data["error"]
                    raise CaptureError(
                        code
                        if isinstance(code, str) and code in DOUYIN_ERRORS
                        else "source_parse_failed"
                    )
                if type(data.get("live")) is not bool:
                    raise CaptureError("source_parse_failed")
                return Source(data["live"], data.get("url"))
            except (ValueError, CaptureError) as error:
                if attempt + 1 == p.probe_attempts:
                    code = error.code if isinstance(error, CaptureError) else "source_parse_failed"
                    raise CaptureError(
                        code if code in DOUYIN_ERRORS else "source_parse_failed"
                    ) from None
                deadline = time.monotonic() + 2**attempt
                while time.monotonic() < deadline:
                    tick()
                    time.sleep(0.1)
        raise CaptureError("source_parse_failed")

    acquire = probe


class FinderProvider:
    def __init__(self, policy):
        self.policy = policy

    def health(self):
        executable = self.policy.finder_executable
        return {
            "dependencies_ready": bool(executable and executable.is_file()),
            "real_platform_verified": False,
            "requires_phone": True,
            "protocol": "dlna",
            "device_name": self.policy.finder_name,
            "receiver_port": self.policy.finder_port,
            "upstream_version": FINDER_VERSION,
        }

    def probe(self, reference, tick):
        canonical_reference("wechat", reference)
        tick()
        return Source(False)

    def acquire(self, reference, tick):
        canonical_reference("wechat", reference)
        if not self.health()["dependencies_ready"]:
            raise CaptureError("provider_dependencies_missing")
        p = self.policy
        output = communicate(
            [
                str(p.finder_executable),
                "--protocol",
                "dlna",
                "--name",
                p.finder_name,
                "--port",
                str(p.finder_port),
            ],
            tick,
            p.wait_seconds,
        )
        url = output.decode().strip()
        if not url.startswith(("http://", "https://")) or "\n" in url:
            raise CaptureError("source_parse_failed")
        return Source(True, url)


class CaptureRegistry:
    def __init__(self, policy, *, douyin_cookie=None):
        self.providers = {
            "douyin": DouyinProvider(policy, cookie=douyin_cookie),
            "wechat": FinderProvider(policy),
        }

    def get(self, platform):
        try:
            return self.providers[platform]
        except KeyError:
            raise CaptureError("unsupported_platform") from None
