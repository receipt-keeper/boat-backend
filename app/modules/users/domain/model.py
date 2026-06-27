from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.validation import Notification
from app.modules.users.domain.value_objects import Email


@dataclass(eq=False)
class User(Entity[UUID]):
    name: str | None
    email: Email | None
    nickname: str | None = None
    profile_image_url: str | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str | None,
        email: str | None,
        user_id: UUID | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
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
        )


@dataclass(eq=False)
class UserSettings(Entity[UUID]):
    terms_version: str | None = None
    privacy_version: str | None = None
    terms_accepted_at: datetime | None = None
    privacy_accepted_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        terms_version: str | None = None,
        privacy_version: str | None = None,
        terms_accepted_at: datetime | None = None,
        privacy_accepted_at: datetime | None = None,
    ) -> "UserSettings":
        return cls(
            id=user_id,
            terms_version=terms_version,
            privacy_version=privacy_version,
            terms_accepted_at=terms_accepted_at,
            privacy_accepted_at=privacy_accepted_at,
        )
