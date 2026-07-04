from functools import lru_cache
from typing import Annotated, Final, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_JWT_SECRET_KEY: Final = "local-development-secret-change-me-32bytes"  # noqa: S105
DEFAULT_REFRESH_TOKEN_PEPPER: Final = "local-refresh-token-pepper-change-me"  # noqa: S105
SECURE_DEPLOYMENT_ENVS: Final = {"staging", "prod"}


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
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key.",
    )
    openrouter_model: str = Field(
        default="google/gemini-3.1-flash-lite",
        description="OpenRouter model for receipt OCR structured extraction.",
    )

    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None
    firebase_check_revoked: bool = False
    firebase_app_name: str = "boat-backend-auth"
    firebase_project_id_option: str = "projectId"
    firebase_uid_claim: str = "uid"
    firebase_subject_claim: str = "sub"
    firebase_email_claim: str = "email"
    firebase_email_verified_claim: str = "email_verified"
    firebase_name_claim: str = "name"
    firebase_namespace_claim: str = "firebase"
    firebase_sign_in_provider_claim: str = "sign_in_provider"
    # Raw Firebase sign_in_provider values -> clean issuer/provider names.
    # This map IS the allowlist: any raw value not present is rejected with 401.
    firebase_provider_normalization_map: dict[str, str] = {
        "google.com": "google",
        "apple.com": "apple",
    }

    push_send_enabled: bool = Field(
        default=False,
        description="FCM 푸시 발송 사용 여부. 꺼져 있으면 발송 없이 알림만 저장한다.",
    )
    push_token_stale_days: int = Field(
        default=60,
        gt=0,
        description="이 일수 이상 갱신되지 않은 푸시 토큰을 정리 배치의 삭제 대상으로 본다.",
    )

    jwt_secret_key: str = Field(
        default=DEFAULT_JWT_SECRET_KEY,
        description="Symmetric key for service access JWT signing.",
    )
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "boat-backend"
    jwt_audience: str = "boat-api"
    access_token_expires_minutes: int = 30

    refresh_token_expires_days: int = 14
    refresh_token_pepper: str = Field(
        default=DEFAULT_REFRESH_TOKEN_PEPPER,
        description="Server-side pepper used when hashing opaque refresh tokens.",
    )

    default_profile_image_url: str | None = None
    file_storage_backend: Literal["local"] = "local"
    file_storage_root: str = "./storage/files"
    file_max_upload_bytes: int = Field(default=10_485_760, gt=0)
    file_max_upload_count: int = Field(default=5, gt=0)
    file_allowed_content_types: Annotated[tuple[str, ...], NoDecode] = (
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
    )

    @field_validator("file_allowed_content_types", mode="before")
    @classmethod
    def split_file_allowed_content_types(cls, value: str | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @model_validator(mode="after")
    def reject_default_token_secrets_for_secure_envs(self) -> Self:
        if self.app_env not in SECURE_DEPLOYMENT_ENVS:
            return self
        if self.jwt_secret_key == DEFAULT_JWT_SECRET_KEY:
            raise ValueError("prod/staging requires a non-default jwt_secret_key")
        if self.refresh_token_pepper == DEFAULT_REFRESH_TOKEN_PEPPER:
            raise ValueError("prod/staging requires a non-default refresh_token_pepper")
        if not self.firebase_check_revoked:
            raise ValueError("prod/staging requires firebase_check_revoked=true")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
