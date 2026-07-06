from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.validation import Notification as ValidationNotification
from app.modules.notifications.domain.events import NotificationCreated
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationKind,
    NotificationMessage,
    NotificationMessageType,
    NotificationMetadata,
    NotificationTitle,
    RegistrationToken,
    ResourceType,
)


def _validate_resource_pair(resource_type: str | None, resource_id: UUID | None) -> None:
    if (resource_type is None) != (resource_id is None):
        raise ValidationError(
            [
                ErrorDetail(
                    field="resource",
                    message="리소스 유형과 리소스 ID는 함께 있거나 함께 없어야 합니다.",
                )
            ]
        )


@dataclass(eq=False)
class UserNotification(AggregateRoot[UUID]):
    user_id: UUID
    message_type: NotificationMessageType
    kind: NotificationKind
    title: NotificationTitle
    message: NotificationMessage
    resource_type: ResourceType | None
    resource_id: UUID | None
    metadata: NotificationMetadata
    created_at: datetime
    read_at: datetime | None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        message_type: NotificationMessageType,
        kind: str,
        title: str,
        message: str,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        metadata: Mapping[str, str] | None = None,
        created_at: datetime,
        read_at: datetime | None = None,
        notification_id: UUID | None = None,
    ) -> "UserNotification":
        created = cls._assemble(
            notification_id=notification_id,
            user_id=user_id,
            message_type=message_type,
            kind=kind,
            title=title,
            message=message,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            created_at=created_at,
            read_at=read_at,
        )
        created.record_event(
            NotificationCreated(
                notification_id=created.id,
                user_id=created.user_id,
                message_type=created.message_type,
                kind=created.kind.value,
                title=created.title.value,
                message=created.message.value,
                resource_type=(
                    created.resource_type.value if created.resource_type is not None else None
                ),
                resource_id=created.resource_id,
            )
        )
        return created

    @classmethod
    def restore(
        cls,
        *,
        notification_id: UUID,
        user_id: UUID,
        message_type: NotificationMessageType,
        kind: str,
        title: str,
        message: str,
        resource_type: str | None,
        resource_id: UUID | None,
        metadata: Mapping[str, str] | None = None,
        created_at: datetime,
        read_at: datetime | None,
    ) -> "UserNotification":
        # 저장된 레코드 복원 전용 — 생성 이벤트를 기록하지 않는다.
        return cls._assemble(
            notification_id=notification_id,
            user_id=user_id,
            message_type=message_type,
            kind=kind,
            title=title,
            message=message,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            created_at=created_at,
            read_at=read_at,
        )

    @classmethod
    def _assemble(
        cls,
        *,
        notification_id: UUID | None,
        user_id: UUID,
        message_type: NotificationMessageType,
        kind: str,
        title: str,
        message: str,
        resource_type: str | None,
        resource_id: UUID | None,
        metadata: Mapping[str, str] | None,
        created_at: datetime,
        read_at: datetime | None,
    ) -> "UserNotification":
        notification = ValidationNotification()
        new_kind = notification.collect(lambda: NotificationKind(kind))
        new_title = notification.collect(lambda: NotificationTitle(title))
        new_message = notification.collect(lambda: NotificationMessage(message))
        new_resource_type = (
            notification.collect(lambda: ResourceType(resource_type))
            if resource_type is not None
            else None
        )
        notification.collect(lambda: _validate_resource_pair(resource_type, resource_id))
        new_metadata = notification.collect(
            lambda: NotificationMetadata(metadata if metadata is not None else {})
        )
        notification.raise_if_any()

        return cls(
            id=notification_id or uuid4(),
            user_id=user_id,
            message_type=message_type,
            kind=new_kind,
            title=new_title,
            message=new_message,
            resource_type=new_resource_type,
            resource_id=resource_id,
            metadata=new_metadata,
            created_at=created_at,
            read_at=read_at,
        )

    def mark_read(self, *, read_at: datetime) -> "UserNotification":
        return UserNotification(
            id=self.id,
            user_id=self.user_id,
            message_type=self.message_type,
            kind=self.kind,
            title=self.title,
            message=self.message,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            metadata=self.metadata,
            created_at=self.created_at,
            read_at=read_at,
        )


@dataclass(eq=False)
class NotificationSettings(Entity[UUID]):
    push_enabled: bool
    marketing_consent: bool

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        push_enabled: bool = True,
        marketing_consent: bool = False,
    ) -> "NotificationSettings":
        return cls(
            id=user_id,
            push_enabled=push_enabled,
            marketing_consent=marketing_consent,
        )


@dataclass(eq=False)
class UserPushToken(Entity[UUID]):
    user_id: UUID
    token: RegistrationToken
    platform: DevicePlatform
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        token: str,
        platform: DevicePlatform,
        created_at: datetime,
        updated_at: datetime,
        push_token_id: UUID | None = None,
    ) -> "UserPushToken":
        notification = ValidationNotification()
        new_token = notification.collect(lambda: RegistrationToken(token))
        notification.raise_if_any()

        return cls(
            id=push_token_id or uuid4(),
            user_id=user_id,
            token=new_token,
            platform=platform,
            created_at=created_at,
            updated_at=updated_at,
        )
