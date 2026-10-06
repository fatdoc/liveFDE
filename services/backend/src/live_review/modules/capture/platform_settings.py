"""Admin-only secret mutations and one bounded, non-recording connection check."""

import shutil
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from live_review.core.auth import CurrentAdmin, MutationAdmin
from live_review.core.errors import ApiError
from live_review.integrations.capture.contracts import CaptureError
from live_review.integrations.capture.policy import load_policy
from live_review.integrations.capture.providers import (
    DOUYIN_ERRORS,
    CaptureRegistry,
    canonical_reference,
)
from live_review.modules.capture.credentials import CredentialStore
from live_review.modules.capture.executor_health import execution_health
from live_review.modules.capture.readiness import platform_conditions

router = APIRouter(prefix="/settings/douyin", tags=["capture"])


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_revision: str = Field(min_length=1, max_length=64, strict=True)


class CookieInput(RevisionInput):
    cookie: SecretStr = Field(repr=False)

    @field_validator("cookie")
    @classmethod
    def valid_cookie(cls, value):
        text = value.get_secret_value().strip()
        if not text or len(text) > 16384 or any(ord(char) < 32 or ord(char) > 126 for char in text):
            raise ValueError("invalid_cookie")
        return SecretStr(text)


class CheckInput(RevisionInput):
    source_ref: str = Field(max_length=200, strict=True)

    @field_validator("source_ref")
    @classmethod
    def valid_source(cls, value):
        try:
            return canonical_reference("douyin", value)
        except CaptureError:
            raise ValueError("invalid_source") from None


def validate_stream_url(url, policy):
    """Static check only: never resolve DNS, fetch media, or rewrite the source URL."""
    try:
        if not isinstance(url, str) or not url or any(ord(c) < 33 or ord(c) == 127 for c in url):
            raise CaptureError("unsafe_stream_url")
        parts = urlsplit(url)
        host = parts.hostname or ""
        if (
            parts.scheme not in {"http", "https"}
            or not host
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or parts.port not in {None, 80, 443}
        ):
            raise CaptureError("unsafe_stream_url")
        if policy.https_only and parts.scheme != "https":
            raise CaptureError("https_required")
        if not any(host == d or host.endswith("." + d) for d in policy.stream_domains):
            raise CaptureError("domain_not_allowed")
    except ValueError:
        raise CaptureError("unsafe_stream_url") from None


def parser_ready(policy):
    # Parser readiness only; this check does not require a recording executor or media tools.
    return bool(
        policy.enabled
        and "douyin" in policy.allowed_platforms
        and CaptureRegistry(policy, douyin_cookie="").get("douyin").health()["dependencies_ready"]
    )


def public(request, snapshot):
    try:
        settings = request.app.state.settings
        policy = load_policy(settings)
        ready = platform_conditions(
            policy,
            "douyin",
            execution_health(settings, policy),
            bool(shutil.which(policy.ffmpeg)),
            bool(shutil.which(policy.ffprobe)),
            douyin_cookie=snapshot.cookie,
        )["start_ready"]
    except CaptureError:
        ready = False
    return snapshot.public(ready)


@router.get("")
def get_settings(request: Request, admin: CurrentAdmin):
    return public(request, CredentialStore(request.app.state.settings, admin.workspace_id).read())


@router.put("")
def put_settings(data: CookieInput, request: Request, admin: MutationAdmin):
    value = CredentialStore(request.app.state.settings, admin.workspace_id).update(
        data.expected_revision, data.cookie.get_secret_value()
    )
    return public(request, value)


@router.delete("")
def clear_settings(data: RevisionInput, request: Request, admin: MutationAdmin):
    value = CredentialStore(request.app.state.settings, admin.workspace_id).update(
        data.expected_revision, ""
    )
    return public(request, value)


@router.post("/check")
def check_settings(data: CheckInput, request: Request, admin: MutationAdmin):
    settings = request.app.state.settings
    store = CredentialStore(settings, admin.workspace_id)
    # A separate process lock permits save/clear while the one parser call is in flight.
    with store.lock("check.lock"):
        snapshot = store.read()
        store.require_revision(snapshot, data.expected_revision)
        if not snapshot.cookie:
            raise ApiError(422, "platform_not_configured", "请先保存平台接入信息")
        policy = load_policy(settings)
        if not parser_ready(policy):
            raise ApiError(503, "provider_dependencies_missing", "平台解析服务尚未就绪")
        provider = CaptureRegistry(
            policy.model_copy(update={"probe_attempts": 1}), douyin_cookie=snapshot.cookie
        ).get("douyin")
        state, error = None, None
        try:
            result = provider.probe(data.source_ref, lambda: None)
            if result.live:
                validate_stream_url(result.url, policy)
            state = "live" if result.live else "not_live"
        except CaptureError as exc:
            error = exc.code if exc.code in DOUYIN_ERRORS else "source_parse_failed"
        except Exception:
            error = "source_parse_failed"
        result = store.finish_check(
            snapshot,
            checked_at=datetime.now(UTC).isoformat(),
            source=data.source_ref,
            state=state,
            error=error,
        )
        return public(request, result)
