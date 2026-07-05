import asyncio
from collections.abc import Sequence
from itertools import batched

import firebase_admin
from firebase_admin import credentials, messaging
from firebase_admin import exceptions as firebase_exceptions

from app.core.config.settings import Settings
from app.core.domain.exceptions import ExternalServiceError
from app.modules.notifications.application.ports.push_sender import (
    PushMessage,
    PushSender,
    PushSendReport,
)
from app.modules.notifications.domain.model import UserPushToken

# 이 응답을 받은 등록은 다시 유효해지지 않으므로 저장소에서 제거 대상으로 보고한다.
_DEAD_REGISTRATION_ERRORS = (messaging.UnregisteredError, messaging.SenderIdMismatchError)

# send_each는 한 번에 500개까지만 받는다. 넘기면 ValueError로 즉시 거부된다.
_SEND_BATCH_LIMIT = 500


class DisabledPushSender(PushSender):
    """푸시 발송이 꺼진 환경(로컬/테스트 등)에서 쓰는 no-op sender."""

    async def send(
        self,
        *,
        tokens: Sequence[UserPushToken],
        message: PushMessage,
    ) -> PushSendReport:
        return PushSendReport()


class FcmPushSender(PushSender):
    def __init__(self, *, app: firebase_admin.App) -> None:
        self._app = app

    @classmethod
    def from_settings(cls, settings: Settings) -> "FcmPushSender":
        try:
            app = firebase_admin.get_app(settings.firebase_app_name)
        except ValueError:
            credential = (
                credentials.Certificate(settings.firebase_credentials_path)
                if settings.firebase_credentials_path
                else credentials.ApplicationDefault()
            )
            options = None
            if settings.firebase_project_id:
                options = {settings.firebase_project_id_option: settings.firebase_project_id}
            app = firebase_admin.initialize_app(
                credential=credential,
                options=options,
                name=settings.firebase_app_name,
            )
        return cls(app=app)

    async def send(
        self,
        *,
        tokens: Sequence[UserPushToken],
        message: PushMessage,
    ) -> PushSendReport:
        invalid_fids: list[str] = []
        for chunk in batched(tokens, _SEND_BATCH_LIMIT):
            fcm_messages = [_to_fcm_message(token, message) for token in chunk]
            try:
                batch = await asyncio.to_thread(messaging.send_each, fcm_messages, app=self._app)
            except firebase_exceptions.FirebaseError as exc:
                raise ExternalServiceError("푸시 발송에 실패했습니다.") from exc

            invalid_fids.extend(
                token.fid.value
                for token, response in zip(chunk, batch.responses, strict=True)
                if isinstance(response.exception, _DEAD_REGISTRATION_ERRORS)
            )
        return PushSendReport(invalid_fids=tuple(invalid_fids))


def _to_fcm_message(token: UserPushToken, message: PushMessage) -> messaging.Message:
    return messaging.Message(
        fid=token.fid.value,
        notification=messaging.Notification(title=message.title, body=message.body),
        data=dict(message.data),
    )
