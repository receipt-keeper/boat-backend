from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.validation import Notification
from app.modules.users.domain.value_objects import (
    Email,
    FreeAnalysisTokensRemaining,
    PushPlatform,
)


@dataclass(eq=False)
class User(Entity[UUID]):
    name: str | None
    email: Email | None
    nickname: str | None = None
    profile_image_url: str | None = None
    profile_image_file_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str | None,
        email: str | None,
        user_id: UUID | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
        profile_image_file_id: UUID | None = None,
    ) -> "User":
        notification = Notification()
        new_email = None if email is None else notification.collect(lambda: Email(email))
        notification.raise_if_any()

        return cls(
            id=user_id or uuid4(),
            name=name,
            email=new_email,
            nickname=nickname,
            profile_image_url=profile_image_url,
            profile_image_file_id=profile_image_file_id,
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
