from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.core.domain.exceptions import ExternalServiceError
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
from app.modules.notifications.domain.value_objects import DevicePlatform

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
        user_notifications = sorted(
            (
                notification
                for notification in self.notifications.values()
                if notification.user_id == user_id
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
        if notification is None:
            return None
        read_notification = notification.mark_read(read_at=read_at)
        self.notifications[notification_id] = read_notification
        return read_notification

    async def get_settings(self, *, user_id: UUID) -> NotificationSettings:
        return self.settings.get(user_id, NotificationSettings.create(user_id=user_id))

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
        self.delete_by_fids_count = 0
        self.delete_by_user_id_count = 0
        self.delete_stale_count = 0

    async def register(
        self,
        *,
        user_id: UUID,
        fid: str,
        platform: DevicePlatform,
    ) -> UserPushToken:
        self.register_count += 1
        now = CREATED_AT
        existing = self.tokens.get(fid)
        saved = UserPushToken.create(
            push_token_id=existing.id if existing is not None else None,
            user_id=user_id,
            fid=fid,
            platform=platform,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self.tokens[fid] = saved
        return saved

    async def unregister(self, *, user_id: UUID, fid: str) -> None:
        self.unregister_count += 1
        existing = self.tokens.get(fid)
        if existing is not None and existing.user_id == user_id:
            del self.tokens[fid]

    async def list_by_user(self, *, user_id: UUID) -> tuple[UserPushToken, ...]:
        return tuple(token for token in self.tokens.values() if token.user_id == user_id)

    async def delete_by_fids(self, *, fids: Sequence[str]) -> None:
        self.delete_by_fids_count += 1
        for fid in fids:
            self.tokens.pop(fid, None)

    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        self.delete_by_user_id_count += 1
        for fid, token in list(self.tokens.items()):
            if token.user_id == user_id:
                del self.tokens[fid]

    async def delete_stale(self, *, older_than: datetime) -> int:
        self.delete_stale_count += 1
        stale_fids = [fid for fid, token in self.tokens.items() if token.updated_at < older_than]
        for fid in stale_fids:
            del self.tokens[fid]
        return len(stale_fids)


class FakePushSender(PushSender):
    def __init__(
        self,
        *,
        report: PushSendReport | None = None,
        error: ExternalServiceError | None = None,
    ) -> None:
        self.calls: list[tuple[tuple[UserPushToken, ...], PushMessage]] = []
        self._report = report if report is not None else PushSendReport()
        self._error = error

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
