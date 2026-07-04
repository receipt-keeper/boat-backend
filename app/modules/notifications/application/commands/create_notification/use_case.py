import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ExternalServiceError
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.result import (
    CreateNotificationResult,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.ports.push_sender import (
    PushMessage,
    PushSender,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.domain.model import UserNotification
from app.modules.notifications.domain.value_objects import NotificationKind

logger = logging.getLogger(__name__)

PUSH_TITLES: Final[dict[NotificationKind, str]] = {
    NotificationKind.WARRANTY_NOTICE: "보증 기간 안내",
    NotificationKind.WARRANTY_WARNING: "보증 만료 주의",
    NotificationKind.WARRANTY_RISK: "보증 만료 임박",
    NotificationKind.WARRANTY_EXPIRED: "보증 만료",
    NotificationKind.REGISTRATION_PROMPT: "영수증 등록 안내",
    NotificationKind.CREDIT_PROMPT: "크레딧 안내",
    NotificationKind.BENEFIT: "혜택 안내",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreateNotificationCommandUseCase:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        push_token_repository: PushTokenRepository,
        push_sender: PushSender,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._notification_repository = notification_repository
        self._push_token_repository = push_token_repository
        self._push_sender = push_sender
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def execute(self, command: CreateNotificationCommand) -> CreateNotificationResult:
        notification = UserNotification.create(
            user_id=command.user_id,
            kind=command.kind,
            message=command.message,
            target_type=command.target_type,
            target_id=command.target_id,
            created_at=self._clock(),
        )
        saved = await self._notification_repository.create(notification=notification)
        await self._unit_of_work.commit()
        await self._send_push(saved)
        return CreateNotificationResult(
            notification_id=saved.id,
            kind=saved.kind,
            message=saved.message.value,
            target_type=saved.target_type,
            target_id=saved.target_id,
            created_at=saved.created_at,
            read_at=saved.read_at,
        )

    async def _send_push(self, notification: UserNotification) -> None:
        settings = await self._notification_repository.get_settings(
            user_id=notification.user_id,
        )
        if not settings.push_enabled:
            return
        tokens = await self._push_token_repository.list_by_user(user_id=notification.user_id)
        if not tokens:
            return

        message = PushMessage(
            title=PUSH_TITLES[notification.kind],
            body=notification.message.value,
            data=_push_data(notification),
        )
        try:
            report = await self._push_sender.send(tokens=tokens, message=message)
        except ExternalServiceError:
            # 푸시는 best-effort — 발송 실패가 알림 생성 자체를 되돌리지 않는다.
            logger.warning("푸시 발송에 실패했습니다. user_id=%s", notification.user_id)
            return

        if report.invalid_tokens:
            await self._push_token_repository.delete_by_fcm_tokens(
                fcm_tokens=report.invalid_tokens,
            )
            await self._unit_of_work.commit()


def _push_data(notification: UserNotification) -> dict[str, str]:
    data = {
        "notificationId": str(notification.id),
        "kind": notification.kind.value,
        "targetType": notification.target_type.value,
    }
    if notification.target_id is not None:
        data["targetId"] = str(notification.target_id)
    return data
