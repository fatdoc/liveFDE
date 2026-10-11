"""Workspace Tencent credentials: atomic private CAS, never a connection test."""

import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from live_review.core.auth import CurrentAdmin, MutationAdmin
from live_review.core.errors import ApiError
from live_review.modules.llm.private_files import PrivateFiles


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(default="16k_zh", pattern=r"^16k_[a-zA-Z0-9_.-]{1,76}$")
    stream_model: Literal["16k_zh_en_2.0", "16k_zh_en_speaker_2.0"] = "16k_zh_en_speaker_2.0"
    timeout_seconds: int = Field(default=120, ge=1, le=600, strict=True)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(min_length=1, max_length=64)


class Input(Parameters, Revision):
    secret_id: SecretStr | None = None
    secret_key: SecretStr | None = None
    app_id: SecretStr | None = None

    @field_validator("secret_id", "secret_key", "app_id")
    @classmethod
    def valid_secret(cls, value, info):
        if value is not None:
            raw = value.get_secret_value()
            if not 1 <= len(raw) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in raw):
                raise ValueError("invalid_credential")
            if info.field_name == "app_id" and (
                not raw.isascii() or not raw.isdigit() or not 5 <= len(raw) <= 20
            ):
                raise ValueError("invalid_app_id")
        return value


class Public(Parameters):
    revision: str = "unconfigured"
    configured: bool = False
    secret_id_configured: bool = False
    secret_key_configured: bool = False
    app_id_configured: bool = False
    max_audio_bytes: int = 5_000_000
    max_duration_seconds: int = 156
    network_checked: bool = False


class State(Parameters):
    revision: str = "unconfigured"
    secret_id: SecretStr = SecretStr("")
    secret_key: SecretStr = SecretStr("")
    app_id: SecretStr = SecretStr("")

    def public(self):
        flags = {
            f"{key}_configured": bool(getattr(self, key).get_secret_value())
            for key in ("secret_id", "secret_key", "app_id")
        }
        return Public(
            **self.model_dump(include={"model", "stream_model", "timeout_seconds"}),
            revision=self.revision,
            configured=flags["secret_id_configured"] and flags["secret_key_configured"],
            **flags,
        )


class Store:
    def __init__(self, settings, workspace_id):
        self.files = PrivateFiles(settings, workspace_id, namespace="asr")

    def read(self):
        raw = self.files.read("tencent.json", 32768)
        try:
            value = State.model_validate_json(raw) if raw else State()
            if raw:
                UUID(value.revision)
            return value
        except ValueError:
            raise ApiError(503, "asr_storage_unavailable", "腾讯识别设置不可用") from None

    def update(self, data=None, *, revision):
        with self.files.lock():
            old = self.read()
            if old.revision != revision:
                raise ApiError(409, "revision_conflict", "配置已变更，请刷新后重试")
            params = (data or old).model_dump(include={"model", "stream_model", "timeout_seconds"})
            secrets = {
                key: (
                    ""
                    if data is None
                    else getattr(data, key).get_secret_value()
                    if getattr(data, key) is not None
                    else getattr(old, key).get_secret_value()
                )
                for key in ("secret_id", "secret_key", "app_id")
            }
            value = State(**params, **secrets, revision=uuid4().hex)
            # One atomic private file: no mixed key pair/revision after interruption.
            self.files.write(
                "tencent.json", json.dumps(params | secrets | {"revision": value.revision}).encode()
            )
            return value.public()


router = APIRouter(prefix="/tencent/settings")


@router.get("", response_model=Public)
def get_settings(request: Request, admin: CurrentAdmin):
    return Store(request.app.state.settings, admin.workspace_id).read().public()


@router.put("", response_model=Public)
def put_settings(data: Input, request: Request, admin: MutationAdmin):
    return Store(request.app.state.settings, admin.workspace_id).update(
        data, revision=data.expected_revision
    )


@router.delete("", response_model=Public)
def delete_settings(data: Revision, request: Request, admin: MutationAdmin):
    return Store(request.app.state.settings, admin.workspace_id).update(
        revision=data.expected_revision
    )
