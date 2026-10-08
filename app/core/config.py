from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tachyon"
    database_url: str
    secret_key: str = Field(min_length=32)
    token_ttl: int = Field(default=60, gt=0)
    log_level: str = "INFO"
    scheduler_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
