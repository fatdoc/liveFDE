from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIVE_", extra="ignore")
    database_url: SecretStr
    broker_url: SecretStr
    service_name: str = "live-review"


@lru_cache
def get_settings() -> Settings:
    return Settings()
