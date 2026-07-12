from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.core.application.event_publisher import EventPublisher
from app.core.domain.events import DomainEvent
from app.modules.notifications.application.ports.notification_repository import (
    NotificationListCursor,
    NotificationListResult,
    NotificationRepository,
)
from app.modules.notifications.application.ports.push_sender import (
    PushMessage,
    PushSender,
    PushSendReport,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.domain.model import (
    NotificationSettings,
    UserNotification,
    UserPushToken,
)
from app.modules.notifications.domain.value_objects import DevicePlatform, NotificationMessageType

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000201")
CREATED_AT = datetime(2026, 6, 28, 1, 2, 3, tzinfo=UTC)
READ_AT = datetime(2026, 6, 28, 4, 5, 6, tzinfo=UTC)


class InMemoryNotificationRepository(NotificationRepository):
    def __init__(self) -> None:
        self.notifications: dict[UUID, UserNotification] = {}
        self.settings: dict[UUID, NotificationSettings] = {}
        self.create_count = 0
        self.mark_read_count = 0
        self.update_settings_count = 0
        self.settings_for_update_count = 0

    async def create(self, *, notification: UserNotification) -> UserNotification:
        self.create_count += 1
        self.notifications[notification.id] = notification
        return notification

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        cursor: NotificationListCursor | None,
        limit: int,
    ) -> NotificationListResult:
        include_marketing = self.settings.get(
            user_id, NotificationSettings.create(user_id=user_id)
        ).marketing_consent
        user_notifications = sorted(
            (
                notification
                for notification in self.notifications.values()
                if notification.user_id == user_id
                and (
                    include_marketing
                    or notification.message_type != NotificationMessageType.MARKETING
                )
            ),
            key=lambda notification: (notification.created_at, notification.id.int),
            reverse=True,
        )
        total_count = len(user_notifications)
        if cursor is not None:
            user_notifications = [
                notification
                for notification in user_notifications
                if (notification.created_at, notification.id.int)
                < (cursor.created_at, cursor.notification_id.int)
            ]
        return NotificationListResult(
            notifications=tuple(user_notifications[:limit]),
            has_next=len(user_notifications) > limit,
            total_count=total_count,
        )

    async def find_by_id_for_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> UserNotification | None:
        notification = self.notifications.get(notification_id)
        if notification is None or notification.user_id != user_id:
            return None
        return notification

    async def mark_read(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
        read_at: datetime,
    ) -> UserNotification | None:
        self.mark_read_count += 1
        notification = await self.find_by_id_for_user(
            notification_id=notification_id,
            user_id=user_id,
        )
        settings = self.settings.get(user_id, NotificationSettings.create(user_id=user_id))
        if (
            notification is not None
            and not settings.marketing_consent
            and (notification.message_type == NotificationMessageType.MARKETING)
        ):
            return None
        if notification is None:
            return None
        read_notification = notification.mark_read(read_at=read_at)
        self.notifications[notification_id] = read_notification
        return read_notification

    async def get_settings(self, *, user_id: UUID) -> NotificationSettings:
        return self.settings.get(user_id, NotificationSettings.create(user_id=user_id))

    async def get_settings_for_update(self, *, user_id: UUID) -> NotificationSettings:
        self.settings_for_update_count += 1
        return await self.get_settings(user_id=user_id)

    async def update_settings(
        self,
        *,
        user_id: UUID,
        push_enabled: bool | None,
        marketing_consent: bool | None,
    ) -> NotificationSettings:
        self.update_settings_count += 1
        current = self.settings.get(user_id, NotificationSettings.create(user_id=user_id))
        updated = NotificationSettings.create(
            user_id=user_id,
            push_enabled=current.push_enabled if push_enabled is None else push_enabled,
            marketing_consent=(
                current.marketing_consent if marketing_consent is None else marketing_consent
            ),
        )
        self.settings[user_id] = updated
        return updated


class InMemoryPushTokenRepository(PushTokenRepository):
    def __init__(self) -> None:
        self.tokens: dict[str, UserPushToken] = {}
        self.register_count = 0
        self.unregister_count = 0
        self.delete_by_tokens_count = 0
        self.delete_by_user_id_count = 0
        self.delete_stale_count = 0

    async def register(
        self,
        *,
        user_id: UUID,
        token: str,
        platform: DevicePlatform,
    ) -> UserPushToken:
        self.register_count += 1
        now = CREATED_AT
        existing = self.tokens.get(token)
        saved = UserPushToken.create(
            push_token_id=existing.id if existing is not None else None,
            user_id=user_id,
            token=token,
            platform=platform,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self.tokens[token] = saved
        return saved

    async def unregister(self, *, user_id: UUID, token: str) -> None:
        self.unregister_count += 1
        existing = self.tokens.get(token)
        if existing is not None and existing.user_id == user_id:
            del self.tokens[token]

    async def list_by_user(self, *, user_id: UUID) -> tuple[UserPushToken, ...]:
        return tuple(token for token in self.tokens.values() if token.user_id == user_id)

    async def delete_by_tokens(self, *, tokens: Sequence[str]) -> None:
        self.delete_by_tokens_count += 1
        for token in tokens:
            self.tokens.pop(token, None)

    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        self.delete_by_user_id_count += 1
        for token, push_token in list(self.tokens.items()):
            if push_token.user_id == user_id:
                del self.tokens[token]

    async def delete_stale(self, *, older_than: datetime) -> int:
        self.delete_stale_count += 1
        stale_tokens = [
            token for token, push_token in self.tokens.items() if push_token.updated_at < older_than
        ]
        for token in stale_tokens:
            del self.tokens[token]
        return len(stale_tokens)


class FakePushSender(PushSender):
    def __init__(
        self,
        *,
        report: PushSendReport | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[tuple[UserPushToken, ...], PushMessage]] = []
        self._report = report if report is not None else PushSendReport()
        self._error: Exception | None = error

    async def send(
        self,
        *,
        tokens: Sequence[UserPushToken],
        message: PushMessage,
    ) -> PushSendReport:
        self.calls.append((tuple(tokens), message))
        if self._error is not None:
            raise self._error
        return self._report


class FakeEventPublisher(EventPublisher):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    async def publish(self, events: Sequence[DomainEvent]) -> None:
        self.published.extend(events)
