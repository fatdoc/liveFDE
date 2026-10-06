from pydantic import BaseModel, ConfigDict, Field, SecretStr

from live_review.integrations.asr_gateway.contracts import ASRError


class TencentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    app_id: str | None = Field(default=None, pattern=r"^[0-9]{5,20}$")
    secret_id: SecretStr = Field(exclude=True, repr=False)
    secret_key: SecretStr = Field(exclude=True, repr=False)
    engine_file: str = Field(pattern=r"^16k_[a-zA-Z0-9_.-]+$")
    engine_stream: str = Field(pattern=r"^16k_zh_en(_speaker)?_2\.0$")
    timeout_seconds: float = Field(default=120, gt=0, le=3600, allow_inf_nan=False)
    io_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    poll_interval_seconds: float = Field(default=1, ge=0.1, le=60, allow_inf_nan=False)
    max_poll_requests: int = Field(default=120, ge=1, le=3600)


def authorize(config, request, *, stream=False):
    if request.allow_network is not True or request.privacy != "cloud_allowed":
        raise ASRError("cloud_not_authorized")
    if not config.secret_id.get_secret_value() or not config.secret_key.get_secret_value():
        raise ASRError("tencent_credentials_missing")
    if request.language != "auto":
        raise ASRError("language_must_be_selected_by_engine")
    if stream:
        if not config.app_id:
            raise ASRError("tencent_app_id_missing")
        if request.emotion:
            raise ASRError("stream_emotion_not_supported")
        if request.speaker and config.engine_stream != "16k_zh_en_speaker_2.0":
            raise ASRError("stream_speaker_engine_required")
        if not request.punctuation:
            raise ASRError("stream_punctuation_control_not_supported")
    else:
        if request.emotion and config.engine_file not in {"16k_zh", "16k_zh_en", "16k_zh_en_2.0"}:
            raise ASRError("file_emotion_engine_not_supported")
        if request.speaker and config.engine_file not in {
            "16k_zh",
            "16k_zh_en",
            "16k_zh_en_2.0",
            "16k_zh_en_meeting",
            "16k_en",
            "16k_ms",
            "16k_id",
            "16k_es",
            "16k_fr",
            "16k_ja",
            "16k_ko",
            "16k_zh_dialect",
        }:
            raise ASRError("file_speaker_engine_not_supported")
