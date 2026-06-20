from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.validation import Notification
from app.core.domain.value_object import ValueObject


@dataclass(frozen=True)
class NormalizedEmail(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if (
            not self.value
            or self.value.strip() != self.value
            or self.value.lower() != self.value
            or "@" not in self.value
            or len(self.value) > self.MAX_LENGTH
        ):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="normalizedEmail",
                        message="정규화된 이메일이 올바르지 않습니다.",
                    )
                ]
            )


@dataclass(frozen=True)
class FreeAnalysisTokensRemaining(ValueObject[int]):
    def validate(self) -> None:
        if self.value < 0:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="freeAnalysisTokensRemaining",
                        message="무료 분석 토큰 수는 0 이상이어야 합니다.",
                    )
                ]
            )


@dataclass(frozen=True)
class PushPlatform(ValueObject[str]):
    ALLOWED: ClassVar[set[str]] = {"android", "ios", "web"}

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError(
                [ErrorDetail(field="platform", message="푸시 플랫폼이 올바르지 않습니다.")]
            )


@dataclass(eq=False)
class User(Entity[UUID]):
    name: str | None
    email: str | None
    normalized_email: NormalizedEmail | None = None
    nickname: str | None = None
    profile_image_url: str | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str | None,
        email: str | None,
        user_id: UUID | None = None,
        normalized_email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> "User":
        notification = Notification()
        new_normalized_email = (
            None
            if normalized_email is None
            else notification.collect(lambda: NormalizedEmail(normalized_email))
        )
        notification.raise_if_any()

        return cls(
            id=user_id or uuid4(),
            name=name,
            email=email,
            normalized_email=new_normalized_email,
            nickname=nickname,
            profile_image_url=profile_image_url,
        )


@dataclass(eq=False)
class UserEntitlement(Entity[UUID]):
    free_analysis_tokens_remaining: FreeAnalysisTokensRemaining

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        free_analysis_tokens_remaining: int = 0,
    ) -> "UserEntitlement":
        return cls(
            id=user_id,
            free_analysis_tokens_remaining=FreeAnalysisTokensRemaining(
                free_analysis_tokens_remaining
            ),
        )


@dataclass(eq=False)
class UserSettings(Entity[UUID]):
    notification_enabled: bool = True
    marketing_consent: bool = False
    terms_version: str | None = None
    privacy_version: str | None = None
    terms_accepted_at: datetime | None = None
    privacy_accepted_at: datetime | None = None
    marketing_consent_updated_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        notification_enabled: bool = True,
        marketing_consent: bool = False,
        terms_version: str | None = None,
        privacy_version: str | None = None,
        terms_accepted_at: datetime | None = None,
        privacy_accepted_at: datetime | None = None,
        marketing_consent_updated_at: datetime | None = None,
    ) -> "UserSettings":
        return cls(
            id=user_id,
            notification_enabled=notification_enabled,
            marketing_consent=marketing_consent,
            terms_version=terms_version,
            privacy_version=privacy_version,
            terms_accepted_at=terms_accepted_at,
            privacy_accepted_at=privacy_accepted_at,
            marketing_consent_updated_at=marketing_consent_updated_at,
        )


@dataclass(eq=False)
class UserPushToken(Entity[UUID]):
    user_id: UUID
    device_id: str
    fcm_token: str
    platform: PushPlatform

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        device_id: str,
        fcm_token: str,
        platform: str,
        push_token_id: UUID | None = None,
    ) -> "UserPushToken":
        return cls(
            id=push_token_id or uuid4(),
            user_id=user_id,
            device_id=device_id,
            fcm_token=fcm_token,
            platform=PushPlatform(platform),
        )
