"""Workspace-only Tencent overlay; public revision pins credentials without exposing them."""

import hashlib

from live_review.core.model_config import LoadedModelConfig
from live_review.core.model_config.asr_routes import TencentASRRoute
from live_review.core.model_config.models import (
    FieldSource,
    ModelAlias,
    ModelDescriptor,
    PublicModelConfig,
)

KEYS = {
    "secret_id": "LIVE_WORKSPACE_ASR_ID",
    "secret_key": "LIVE_WORKSPACE_ASR_KEY",
    "app_id": "LIVE_WORKSPACE_ASR_APP",
}


def overlay(loaded, state, workspace_id):
    route = TencentASRRoute(
        protocol="tencent_asr",
        enabled=state.public().configured,
        model=state.model,
        stream_model=state.stream_model,
        timeout_seconds=state.timeout_seconds,
        key_env=KEYS["secret_key"],
        secret_id_env=KEYS["secret_id"],
        app_id_env=KEYS["app_id"],
    )
    model = ModelDescriptor(name="workspace_tencent_asr", capability="asr", route=route)
    content = loaded.public.model_dump(mode="python")
    content["models"] = tuple(m for m in loaded.public.models if m.name != model.name) + (model,)
    content["aliases"] = tuple(a for a in loaded.public.aliases if a.name != "asr.tencent") + (
        ModelAlias(name="asr.tencent", model=model.name),
    )
    content["revision"] = hashlib.sha256(
        f"{loaded.public.revision}:{workspace_id}:{state.revision}".encode()
    ).hexdigest()
    return LoadedModelConfig(
        public=PublicModelConfig.model_validate(content),
        provenance=loaded.provenance
        + (FieldSource(field_path="models.workspace_tencent_asr", source="workspace"),),
        config_dir=loaded.config_dir,
        local_path=loaded.local_path,
        dotenv_path=loaded.dotenv_path,
        credential_values=tuple(
            (k, v) for k, v in loaded.credential_values if k not in KEYS.values()
        )
        + tuple((env, getattr(state, name)) for name, env in KEYS.items()),
    )
