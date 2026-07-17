import logging
from collections.abc import Mapping
from typing import Final

from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
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
from app.modules.notifications.domain.value_objects import NotificationMessageType

logger = logging.getLogger(__name__)

_LEGACY_SCHEDULER_KIND_ALIASES: Final[Mapping[str, str]] = {
    "warranty": "warranty_expiry",
    "engagement_unregistered_receipt": "receipt_registration_reminder",
    "engagement_inactive_receipt": "receipt_inactivity_reminder",
    "engagement_all_user": "receipt_analysis_reminder",
}


class SendNotificationPushCommandUseCase:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        push_token_repository: PushTokenRepository,
        push_sender: PushSender,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._notification_repository = notification_repository
        self._push_token_repository = push_token_repository
        self._push_sender = push_sender
        self._unit_of_work = unit_of_work

    async def execute(self, command: SendNotificationPushCommand) -> None:
        # 푸시는 best-effort — 이미 생성된 알림이 발송/정리 실패의 영향을 받으면 안 된다.
        try:
            notification = await self._notification_repository.find_by_id_for_user(
                notification_id=command.notification_id,
                user_id=command.user_id,
            )
            if notification is None:
                return
            settings = await self._notification_repository.get_settings(user_id=command.user_id)
            if not settings.push_enabled:
                return
            is_unconsented_marketing = (
                command.message_type == NotificationMessageType.MARKETING
                and not settings.marketing_consent
            )
            if is_unconsented_marketing:
                return
            tokens = await self._push_token_repository.list_by_user(user_id=command.user_id)
            if not tokens:
                return

            message = PushMessage(
                title=command.title,
                body=command.message,
                data=_push_data(command),
            )
            report = await self._push_sender.send(tokens=tokens, message=message)
            if report.invalid_tokens:
                await self._push_token_repository.delete_by_tokens(tokens=report.invalid_tokens)
                await self._unit_of_work.commit()
        except Exception:
            logger.warning(
                "푸시 발송 또는 무효 등록 정리에 실패했습니다. user_id=%s",
                command.user_id,
                exc_info=True,
            )


def _push_data(command: SendNotificationPushCommand) -> dict[str, str]:
    data = {
        "notificationId": str(command.notification_id),
        "category": command.category.value,
        "messageType": command.message_type.value,
        "kind": _LEGACY_SCHEDULER_KIND_ALIASES.get(command.kind, command.kind),
    }
    if command.resource_type is not None:
        data["resourceType"] = command.resource_type
    if command.resource_id is not None:
        data["resourceId"] = str(command.resource_id)
    return data
