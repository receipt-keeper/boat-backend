from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.validation import Notification
from app.modules.users.domain.events import UserProfileImageChanged, UserRegistered
from app.modules.users.domain.value_objects import Email


@dataclass(eq=False)
class User(AggregateRoot[UUID]):
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
        created = cls._assemble(
            user_id=user_id,
            name=name,
            email=email,
            nickname=nickname,
            profile_image_url=profile_image_url,
        )
        created.record_event(
            UserRegistered(
                user_id=created.id,
                email=None if created.email is None else created.email.value,
                name=created.name,
            )
        )
        return created

    @classmethod
    def restore(
        cls,
        *,
        user_id: UUID,
        name: str | None,
        email: str | None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> "User":
        # 저장된 레코드 복원 전용 — 생성 이벤트를 기록하지 않는다.
        return cls._assemble(
            user_id=user_id,
            name=name,
            email=email,
            nickname=nickname,
            profile_image_url=profile_image_url,
        )

    @classmethod
    def _assemble(
        cls,
        *,
        user_id: UUID | None,
        name: str | None,
        email: str | None,
        nickname: str | None,
        profile_image_url: str | None,
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

    def update_profile_image_url(self, *, profile_image_url: str | None) -> "User":
        previous_image_url = self.profile_image_url
        updated = User(
            id=self.id,
            name=self.name,
            email=self.email,
            nickname=self.nickname,
            profile_image_url=profile_image_url,
        )
        updated.record_event(
            UserProfileImageChanged(
                user_id=self.id,
                previous_image_url=previous_image_url,
                new_image_url=profile_image_url,
            )
        )
        return updated


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
