"""Single SDK boundary; workspace preferences choose registered names, never URLs/paths."""

from live_review.core.model_config import load_model_config
from live_review.core.model_registry import ModelRegistry
from live_review.integrations.asr_gateway.contracts import ASRError
from live_review.workers.media_configuration import config_environment

MODEL_IDS = {"local": "asr.local", "tencent": "asr.tencent"}


def registry_for(settings):
    if settings.model_config_dir is None:
        raise ASRError("model_configuration_missing")
    loaded = load_model_config(
        settings.model_config_dir,
        environment=config_environment(settings, settings.model_config_environment),
        dotenv_path=settings.model_dotenv_path,
    )
    return ModelRegistry(loaded)


def create_provider(registry, provider):
    if provider not in MODEL_IDS:
        raise ASRError("provider_not_registered")
    model = registry.get(MODEL_IDS[provider])
    if model.capability != "asr" or not model.route.enabled:
        raise ASRError("asr_provider_disabled")
    route = model.route
    if provider == "local" and route.protocol == "local_funasr":
        from live_review.integrations.asr_gateway.local.config import LocalConfig
        from live_review.integrations.asr_gateway.local_worker import LocalWorkerProvider

        if route.worker_socket is None:
            raise ASRError("local_worker_socket_required")

        values = route.model_dump(
            exclude={"protocol", "enabled", "provider", "key_env", "model", "worker_socket"}
        )
        values["asr_model"] = route.model
        return LocalWorkerProvider(route.worker_socket, LocalConfig(**values))
    if provider == "tencent" and route.protocol == "tencent_asr":
        from live_review.integrations.asr_gateway.tencent import TencentASRProvider, TencentConfig

        secret_id = registry.loaded.credential(route.secret_id_env)
        secret_key = registry.loaded.credential(route.key_env)
        if not secret_id or not secret_key:
            raise ASRError("tencent_credentials_missing")
        return TencentASRProvider(
            TencentConfig(
                app_id=registry.loaded.credential(route.app_id_env),
                secret_id=secret_id,
                secret_key=secret_key,
                engine_file=route.model,
                engine_stream=route.stream_model,
                timeout_seconds=route.timeout_seconds,
                poll_interval_seconds=route.poll_interval_seconds,
                max_poll_requests=route.max_poll_requests,
                io_timeout_seconds=route.io_timeout_seconds,
            )
        )
    raise ASRError("provider_protocol_mismatch")
