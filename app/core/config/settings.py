from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "test", "dev", "staging", "prod"] = "local"
    app_name: str = "Boat Backend"
    api_prefix: str = "/api/v1"

    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str | None = "/openapi.json"

    database_url: str = Field(
        default="postgresql+asyncpg://boat:boat@localhost:5432/boat",
        description="Async SQLAlchemy database URL.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
