from functools import lru_cache
from typing import Annotated, Final, Literal, Self, assert_never

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_JWT_SECRET_KEY: Final = "local-development-secret-change-me-32bytes"  # noqa: S105
DEFAULT_REFRESH_TOKEN_PEPPER: Final = "local-refresh-token-pepper-change-me"  # noqa: S105
DEFAULT_PROMOTION_BENEFICIARY_HMAC_SECRET: Final = "local-promotion-beneficiary-hmac-change-me"  # noqa: S105
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

    outbox_poller_enabled: bool = Field(
        default=True,
        description="lifespan에서 outbox 재발행 폴러(OutboxRelay.run_forever)를 시작할지 여부.",
    )
    outbox_poll_interval_seconds: float = Field(
        default=2.0,
        description="outbox 폴러가 재발행 대상을 조회하는 주기(초).",
    )
    outbox_batch_size: int = Field(
        default=100,
        description="outbox 폴러가 한 번에 조회·재발행하는 최대 row 수.",
    )
    outbox_redeliver_after_seconds: int = Field(
        default=30,
        description="즉시 발행 경로와 경합을 피해 폴러가 재발행 대상으로 삼는 최소 경과 시간(초).",
    )
    outbox_max_retry: int = Field(
        default=10,
        description="이 횟수 이상 실패한 row는 폴러 조회 대상에서 제외한다(잔존 row=dead letter).",
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
    promotion_beneficiary_hmac_secret: str = Field(
        default=DEFAULT_PROMOTION_BENEFICIARY_HMAC_SECRET,
        min_length=1,
        description=(
            "프로모션 수혜자 식별 HMAC 비밀값. v1 non-null beneficiary row가 하나라도 "
            "존재하는 동안 변경하지 않는다. rotation/keyring/data migration은 별도 절차다."
        ),
    )

    default_profile_image_url: str | None = None
    file_storage_backend: Literal["local", "s3"] = "local"
    file_storage_root: str = "./storage/files"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
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

    @field_validator("promotion_beneficiary_hmac_secret")
    @classmethod
    def reject_blank_promotion_beneficiary_hmac_secret(cls, value: str) -> str:
        if value.strip() != value:
            raise PydanticCustomError(
                "promotion_beneficiary_hmac_secret_whitespace",
                "promotion_beneficiary_hmac_secret must not have surrounding whitespace",
            )
        return value

    @model_validator(mode="after")
    def reject_default_token_secrets_for_secure_envs(self) -> Self:
        if self.app_env not in SECURE_DEPLOYMENT_ENVS:
            return self
        if self.jwt_secret_key == DEFAULT_JWT_SECRET_KEY:
            raise ValueError("prod/staging requires a non-default jwt_secret_key")
        if self.refresh_token_pepper == DEFAULT_REFRESH_TOKEN_PEPPER:
            raise ValueError("prod/staging requires a non-default refresh_token_pepper")
        if self.promotion_beneficiary_hmac_secret == DEFAULT_PROMOTION_BENEFICIARY_HMAC_SECRET:
            raise ValueError(
                "prod/staging requires a non-default promotion_beneficiary_hmac_secret"
            )
        if not self.firebase_check_revoked:
            raise ValueError("prod/staging requires firebase_check_revoked=true")
        return self

    @model_validator(mode="after")
    def validate_file_storage_configuration(self) -> Self:
        match self.file_storage_backend:
            case "local":
                return self
            case "s3":
                if not self.s3_bucket or not self.s3_bucket.strip() or not self.s3_region:
                    raise ValueError("FILE_STORAGE_BACKEND=s3 requires S3_BUCKET and S3_REGION")
                has_access_key = bool(self.s3_access_key_id and self.s3_access_key_id.strip())
                has_secret_key = bool(
                    self.s3_secret_access_key and self.s3_secret_access_key.strip()
                )
                if has_access_key != has_secret_key:
                    raise ValueError(
                        "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be configured together"
                    )
                return self
            case unreachable:
                assert_never(unreachable)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
