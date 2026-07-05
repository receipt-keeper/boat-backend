import asyncio
import warnings
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
        invalid_tokens: list[str] = []
        for chunk in batched(tokens, _SEND_BATCH_LIMIT):
            fcm_messages = [_to_fcm_message(token, message) for token in chunk]
            try:
                batch = await asyncio.to_thread(messaging.send_each, fcm_messages, app=self._app)
            except firebase_exceptions.FirebaseError as exc:
                raise ExternalServiceError("푸시 발송에 실패했습니다.") from exc

            invalid_tokens.extend(
                token.token.value
                for token, response in zip(chunk, batch.responses, strict=True)
                if isinstance(response.exception, _DEAD_REGISTRATION_ERRORS)
            )
        return PushSendReport(invalid_tokens=tuple(invalid_tokens))


def _to_fcm_message(token: UserPushToken, message: PushMessage) -> messaging.Message:
    # firebase-admin 7.5.0에서 Message.token은 DeprecationWarning을 발생시키지만,
    # 클라이언트(Samsung SMP 래퍼)가 신규 FID 등록 경로를 생성하지 않아 FID 발송이
    # 수신되지 않는 것이 실측 확정됐다. token 발송은 deprecated지만 제거 공지가 없고
    # 실제로 동작하므로 의도적으로 사용한다(FID 전환 롤백). pyproject의
    # filterwarnings=["error"]가 이 경고를 예외로 승격시키므로 이 생성 지점에서만
    # 국소적으로 억제한다.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return messaging.Message(
            token=token.token.value,
            notification=messaging.Notification(title=message.title, body=message.body),
            data=dict(message.data),
        )
