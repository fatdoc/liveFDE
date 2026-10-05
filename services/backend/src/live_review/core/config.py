from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIVE_", extra="ignore")
    database_url: SecretStr
    broker_url: SecretStr
    storage_root: Path | None = None
    upload_max_bytes: int = 536870912
    upload_ttl_seconds: int = 86400
    upload_lease_seconds: int = 300
    ffprobe_path: str = "ffprobe"
    service_name: str = "live-review"

    environment: str = "development"
    trusted_origins: list[str] = ["http://127.0.0.1:5188", "http://localhost:5188"]
    session_ttl_seconds: int = 28800
    login_limit: int = 10
    login_window_seconds: int = 900

    @model_validator(mode="after")
    def validate_auth_config(self):
        if self.environment not in {"development", "production"}:
            raise ValueError("Unsupported environment")
        if not self.trusted_origins or any(
            origin.endswith("/") or "*" in origin or not origin.startswith(("http://", "https://"))
            for origin in self.trusted_origins
        ):
            raise ValueError("Configure exact trusted origins without trailing slash")
        if self.environment == "production" and any(
            not origin.startswith("https://") for origin in self.trusted_origins
        ):
            raise ValueError("Production requires HTTPS origins")
        if min(self.session_ttl_seconds, self.login_limit, self.login_window_seconds) < 1:
            raise ValueError("Authentication limits must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
