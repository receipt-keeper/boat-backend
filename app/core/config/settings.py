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

    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None
    firebase_check_revoked: bool = False
    firebase_app_name: str = "boat-backend-auth"
    firebase_project_id_option: str = "projectId"
    firebase_issuer: str = "firebase"
    firebase_default_provider: str = "firebase"
    firebase_uid_claim: str = "uid"
    firebase_subject_claim: str = "sub"
    firebase_email_claim: str = "email"
    firebase_name_claim: str = "name"
    firebase_namespace_claim: str = "firebase"
    firebase_sign_in_provider_claim: str = "sign_in_provider"

    jwt_secret_key: str = Field(
        default="local-development-secret-change-me-32bytes",
        description="Symmetric key for service access JWT signing.",
    )
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "boat-backend"
    jwt_audience: str = "boat-api"
    access_token_expires_minutes: int = 30

    refresh_token_expires_days: int = 14
    refresh_token_pepper: str = Field(
        default="local-refresh-token-pepper-change-me",
        description="Server-side pepper used when hashing opaque refresh tokens.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
