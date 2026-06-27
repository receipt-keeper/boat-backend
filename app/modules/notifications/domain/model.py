from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.validation import Notification as ValidationNotification
from app.modules.notifications.domain.value_objects import (
    NotificationKind,
    NotificationMessage,
    NotificationTargetType,
)


@dataclass(eq=False)
class UserNotification(Entity[UUID]):
    user_id: UUID
    kind: NotificationKind
    message: NotificationMessage
    target_type: NotificationTargetType
    target_id: UUID | None
    created_at: datetime
    read_at: datetime | None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        kind: NotificationKind,
        message: str,
        target_type: NotificationTargetType = NotificationTargetType.NONE,
        target_id: UUID | None = None,
        created_at: datetime,
        read_at: datetime | None = None,
        notification_id: UUID | None = None,
    ) -> "UserNotification":
        notification = ValidationNotification()
        new_message = notification.collect(lambda: NotificationMessage(message))
        notification.raise_if_any()

        return cls(
            id=notification_id or uuid4(),
            user_id=user_id,
            kind=kind,
            message=new_message,
            target_type=target_type,
            target_id=target_id,
            created_at=created_at,
            read_at=read_at,
        )

    def mark_read(self, *, read_at: datetime) -> "UserNotification":
        return UserNotification(
            id=self.id,
            user_id=self.user_id,
            kind=self.kind,
            message=self.message,
            target_type=self.target_type,
            target_id=self.target_id,
            created_at=self.created_at,
            read_at=read_at,
        )


@dataclass(eq=False)
class NotificationPreference(Entity[UUID]):
    push_enabled: bool
    marketing_consent: bool

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        push_enabled: bool = True,
        marketing_consent: bool = False,
    ) -> "NotificationPreference":
        return cls(
            id=user_id,
            push_enabled=push_enabled,
            marketing_consent=marketing_consent,
        )
