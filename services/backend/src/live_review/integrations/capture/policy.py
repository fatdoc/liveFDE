"""Separate layered policy; never changes the existing model snapshot hash."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from live_review.core.model_config import deep_merge
from live_review.core.model_config.safe_io import read_yaml
from live_review.integrations.capture.contracts import CaptureError
from live_review.workers.media_configuration import config_environment


class CapturePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(default=1, ge=1, le=1)
    enabled: bool = False
    https_only: bool = False
    allowed_platforms: list[Literal["douyin", "wechat"]] = Field(
        default_factory=lambda: ["douyin", "wechat"]
    )
    execution_mode: Literal["operator", "native"] = "operator"
    root: Path | None = None
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    douyin_python: Path | None = None
    douyin_checkout: Path | None = None
    douyin_cookie_env: str = "LIVE_CAPTURE_DOUYIN_COOKIE"
    finder_executable: Path | None = None
    finder_name: str = Field(default="FDE Capture", pattern=r"^[\w -]{1,40}$")
    finder_port: int = Field(default=8198, ge=1024, le=65535)
    wait_seconds: int = Field(default=300, ge=1, le=3600)
    probe_seconds: int = Field(default=30, ge=1, le=60)
    probe_attempts: int = Field(default=2, ge=1, le=3)
    max_seconds: int = Field(default=14400, ge=1, le=86400)
    min_free_bytes: int = Field(default=1073741824, ge=1048576)
    max_bytes: int = Field(default=500000000, ge=1048576)
    stall_seconds: int = Field(default=30, ge=2, le=300)
    stream_domains: list[str] = Field(
        default_factory=lambda: [
            "douyincdn.com",
            "douyinvod.com",
            "bytecdn.cn",
            "bytecdn.com",
            "bytefcdnrd.com",
            "amemv.com",
            "myqcloud.com",
            "qq.com",
        ]
    )


def load_policy(settings):
    directory = settings.model_config_dir
    merged = {}
    if directory:
        environment = config_environment(settings, settings.model_config_environment)
        paths = [
            directory / "capture-policy.yaml",
            directory / "environments" / f"{environment}.capture.yaml",
        ]
        if environment in {"development", "test"}:
            paths.append(directory / "capture.local.yaml")
        for path in paths:
            if path.exists() or path.is_symlink():
                merged = deep_merge(merged, read_yaml(path))
    try:
        return CapturePolicy.model_validate(merged)
    except ValidationError:
        raise CaptureError("invalid_capture_policy") from None


def require_enabled(policy):
    if not policy.enabled or policy.root is None or not policy.root.is_absolute():
        raise CaptureError("capture_not_configured")


def fingerprint(policy):
    content = json.dumps(policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()
