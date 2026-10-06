"""Bounded no-interpolation YAML and dotenv reads; safe constant error codes only."""

import os
import re
import stat
from pathlib import Path

import yaml
from yaml.events import (
    AliasEvent,
    MappingEndEvent,
    MappingStartEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

from live_review.core.provider_config import MAX_BYTES, ProviderConfigError, StrictLoader


def read_text(path: Path, *, private=False) -> str:
    try:
        if not path.is_absolute() or path.resolve() != path or "$" in str(path):
            raise ProviderConfigError("invalid_config_path")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or (private and info.st_mode & 0o077):
                raise ProviderConfigError("unsafe_private_configuration")
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ProviderConfigError("config_too_large")
        return raw.decode("utf-8")
    except (OSError, UnicodeError):
        raise ProviderConfigError("configuration_read_failed") from None


def reject_secret_fields(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ProviderConfigError("invalid_mapping")
            normalized = key.lower()
            if normalized.endswith("_env"):
                if child is not None and not (
                    isinstance(child, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", child)
                ):
                    raise ProviderConfigError("invalid_environment_reference")
            elif normalized in {
                "api_key",
                "key",
                "password",
                "secret",
                "token",
                "credentials",
                "authorization",
                "access_token",
                "access_key",
                "private_key",
            }:
                raise ProviderConfigError("plaintext_secret_forbidden")
            reject_secret_fields(child)
    elif isinstance(value, str) and any(marker in value for marker in ("${", "$(", "`")):
        raise ProviderConfigError("yaml_interpolation_forbidden")
    elif isinstance(value, list):
        for child in value:
            reject_secret_fields(child)


def read_yaml(path):
    try:
        text = read_text(path)
        depth = 0
        for count, event in enumerate(yaml.parse(text, Loader=StrictLoader), start=1):
            if count > 4096 or isinstance(event, AliasEvent) or getattr(event, "anchor", None):
                raise ProviderConfigError("yaml_complexity_rejected")
            if getattr(event, "tag", None):
                raise ProviderConfigError("yaml_tags_rejected")
            if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
                depth += 1
                if depth > 12:
                    raise ProviderConfigError("yaml_depth_rejected")
            if isinstance(event, (MappingEndEvent, SequenceEndEvent)):
                depth -= 1
        data = yaml.load(text, Loader=StrictLoader)
        if not isinstance(data, dict):
            raise ProviderConfigError("yaml_mapping_required")
        reject_secret_fields(data)  # Every source, BEFORE overriding/merging.
        return data
    except ProviderConfigError:
        raise
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        raise ProviderConfigError("invalid_registry_yaml") from None


def read_dotenv(path):
    values = {}
    for line in read_text(path, private=True).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ProviderConfigError("invalid_dotenv")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", key) or key in values:
            raise ProviderConfigError("invalid_dotenv")
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise ProviderConfigError("invalid_dotenv")
            value = value[1:-1]
        if "$" in value or "`" in value or "\\" in value or len(value) > 8192:
            raise ProviderConfigError("dotenv_interpolation_forbidden")
        values[key] = value
    return values
