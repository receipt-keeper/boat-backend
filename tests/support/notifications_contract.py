from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

from fastapi import FastAPI, Request

from app.core.config.settings import Settings
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.result import (
    CreateNotificationResult,
)
from app.modules.notifications.application.commands.mark_notification_read.command import (
    MarkNotificationReadCommand,
)
from app.modules.notifications.application.commands.mark_notification_read.result import (
    MarkNotificationReadResult,
)
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.result import (
    UpdateNotificationSettingsResult,
)
from app.modules.notifications.application.queries.get_notification_settings.query import (
    GetNotificationSettingsQuery,
)
from app.modules.notifications.application.queries.get_notification_settings.result import (
    GetNotificationSettingsResult,
)
from app.modules.notifications.application.queries.list_notifications.query import (
    ListNotificationsQuery,
)
from app.modules.notifications.application.queries.list_notifications.result import (
    ListNotificationsResult,
    NotificationListItemResult,
)
from app.modules.notifications.dependencies import (
    get_create_notification_command_use_case,
    get_list_notifications_query_use_case,
    get_mark_notification_read_command_use_case,
    get_notification_settings_query_use_case,
    get_update_notification_settings_command_use_case,
)
from app.modules.notifications.domain.value_objects import NotificationCategory

TEST_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000101")
TEST_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000102")
TEST_SESSION_ID: Final = UUID("00000000-0000-0000-0000-000000000103")
TEST_SETTINGS: Final = Settings(app_name="Boat Backend")


@dataclass(frozen=True, slots=True)
class StoredNotification:
    notification_id: UUID
    user_id: UUID
    category: NotificationCategory
    kind: str
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
    created_at: datetime
    read_at: datetime | None = None


class Executable[CommandT, ResultT]:
    def __init__(self, handler: Callable[[CommandT], ResultT]) -> None:
        self._handler = handler

    async def execute(self, value: CommandT) -> ResultT:
        return self._handler(value)


class NotificationsContractStore:
    def __init__(self) -> None:
        self._notifications: list[StoredNotification] = []
        self._push_enabled = True
        self._marketing_consent = False

    def create(self, command: CreateNotificationCommand) -> CreateNotificationResult:
        notification = StoredNotification(
            notification_id=uuid4(),
            user_id=command.user_id,
            category=command.category,
            kind=command.kind,
            title=command.title,
            message=command.message,
            resource_type=command.resource_type,
            resource_id=command.resource_id,
            created_at=datetime(2026, 6, 28, 9, 0, tzinfo=UTC)
            + timedelta(seconds=len(self._notifications)),
        )
        self._notifications.append(notification)
        return CreateNotificationResult(
            notification_id=notification.notification_id,
            category=notification.category,
            kind=notification.kind,
            title=notification.title,
            message=notification.message,
            resource_type=notification.resource_type,
            resource_id=notification.resource_id,
            created_at=notification.created_at,
            read_at=notification.read_at,
        )

    def list_notifications(self, query: ListNotificationsQuery) -> ListNotificationsResult:
        user_notifications = sorted(
            (
                notification
                for notification in self._notifications
                if notification.user_id == query.user_id
            ),
            key=lambda notification: (notification.created_at, notification.notification_id),
            reverse=True,
        )
        candidates = user_notifications
        if query.cursor:
            cursor_created_at, cursor_id = _parse_contract_cursor(query.cursor)
            candidates = [
                notification
                for notification in user_notifications
                if (notification.created_at, notification.notification_id)
                < (cursor_created_at, cursor_id)
            ]
        page = candidates[: query.limit]
        has_next = len(candidates) > query.limit
        next_cursor = _format_contract_cursor(page[-1]) if has_next and page else None
        return ListNotificationsResult(
            notifications=tuple(_list_item(notification) for notification in page),
            next_cursor=next_cursor,
            has_next=has_next,
            limit=query.limit,
            total_count=len(user_notifications),
        )

    def mark_read(self, command: MarkNotificationReadCommand) -> MarkNotificationReadResult:
        read_at = datetime(2026, 6, 28, 10, 0, tzinfo=UTC)
        for index, notification in enumerate(self._notifications):
            if (
                notification.user_id == command.user_id
                and notification.notification_id == command.notification_id
            ):
                read_notification = replace(notification, read_at=read_at)
                self._notifications[index] = read_notification
                return MarkNotificationReadResult(
                    notification_id=read_notification.notification_id,
                    category=read_notification.category,
                    kind=read_notification.kind,
                    title=read_notification.title,
                    message=read_notification.message,
                    resource_type=read_notification.resource_type,
                    resource_id=read_notification.resource_id,
                    created_at=read_notification.created_at,
                    read_at=read_notification.read_at,
                )
        raise AssertionError("notification contract test attempted to read a missing notification")

    def get_settings(self, query: GetNotificationSettingsQuery) -> GetNotificationSettingsResult:
        _ = query
        return GetNotificationSettingsResult(
            push_enabled=self._push_enabled,
            marketing_consent=self._marketing_consent,
        )

    def update_settings(
        self,
        command: UpdateNotificationSettingsCommand,
    ) -> UpdateNotificationSettingsResult:
        if command.push_enabled is not None:
            self._push_enabled = command.push_enabled
        if command.marketing_consent is not None:
            self._marketing_consent = command.marketing_consent
        return UpdateNotificationSettingsResult(
            push_enabled=self._push_enabled,
            marketing_consent=self._marketing_consent,
        )


_CONTRACT_CURSOR_SEPARATOR: Final = "|"


def _parse_contract_cursor(cursor: str) -> tuple[datetime, UUID]:
    created_at_text, _, notification_id_text = cursor.partition(_CONTRACT_CURSOR_SEPARATOR)
    created_at = datetime.fromisoformat(created_at_text.replace("Z", "+00:00"))
    return created_at, UUID(notification_id_text)


def _format_contract_cursor(notification: StoredNotification) -> str:
    created_at_text = notification.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"{created_at_text}{_CONTRACT_CURSOR_SEPARATOR}{notification.notification_id}"


def _list_item(notification: StoredNotification) -> NotificationListItemResult:
    return NotificationListItemResult(
        notification_id=notification.notification_id,
        category=notification.category,
        kind=notification.kind,
        title=notification.title,
        message=notification.message,
        resource_type=notification.resource_type,
        resource_id=notification.resource_id,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


async def _fake_authenticate_current_principal(request: Request) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )
    set_current_principal(request, principal)
    return principal


def create_notifications_contract_app() -> FastAPI:
    test_app = create_app(TEST_SETTINGS)
    notifications = NotificationsContractStore()
    test_app.dependency_overrides[authenticate_current_principal] = (
        _fake_authenticate_current_principal
    )
    test_app.dependency_overrides[get_create_notification_command_use_case] = lambda: Executable(
        notifications.create
    )
    test_app.dependency_overrides[get_list_notifications_query_use_case] = lambda: Executable(
        notifications.list_notifications
    )
    test_app.dependency_overrides[get_mark_notification_read_command_use_case] = lambda: Executable(
        notifications.mark_read
    )
    test_app.dependency_overrides[get_notification_settings_query_use_case] = lambda: Executable(
        notifications.get_settings
    )
    test_app.dependency_overrides[get_update_notification_settings_command_use_case] = lambda: (
        Executable(notifications.update_settings)
    )
    return test_app
