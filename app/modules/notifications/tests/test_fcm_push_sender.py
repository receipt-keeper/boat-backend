from typing import Any, cast
from uuid import uuid4

import firebase_admin
import pytest
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging

from app.core.domain.exceptions import ExternalServiceError
from app.modules.notifications.application.ports.push_sender import PushMessage
from app.modules.notifications.domain.model import UserPushToken
from app.modules.notifications.domain.value_objects import DevicePlatform
from app.modules.notifications.infrastructure.fcm.push_sender import (
    DisabledPushSender,
    FcmPushSender,
)
from app.modules.notifications.tests.test_application import CREATED_AT


class _FakeSendResponse:
    def __init__(self, exception: Exception | None) -> None:
        self.exception = exception


class _FakeBatchResponse:
    def __init__(self, responses: list[_FakeSendResponse]) -> None:
        self.responses = responses


def _push_token(*, fid: str, platform: DevicePlatform) -> UserPushToken:
    return UserPushToken.create(
        user_id=uuid4(),
        fid=fid,
        platform=platform,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def _sender() -> FcmPushSender:
    return FcmPushSender(app=cast(firebase_admin.App, object()))


async def test_fcm_push_sender_builds_messages_and_reports_dead_registrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 살아 있는 등록과 해제된 등록이 섞여 있다.
    tokens = [
        _push_token(fid="fid-live", platform=DevicePlatform.ANDROID),
        _push_token(fid="fid-dead", platform=DevicePlatform.IOS),
    ]
    sent_batches: list[list[messaging.Message]] = []

    def fake_send_each(
        fcm_messages: list[messaging.Message],
        *,
        app: firebase_admin.App,
    ) -> _FakeBatchResponse:
        sent_batches.append(fcm_messages)
        return _FakeBatchResponse(
            [
                _FakeSendResponse(None),
                _FakeSendResponse(messaging.UnregisteredError("죽은 등록")),
            ]
        )

    monkeypatch.setattr(messaging, "send_each", fake_send_each)
    message = PushMessage(
        title="혜택 안내",
        body="이번 달 혜택을 확인해 보세요.",
        data={"kind": "benefit"},
    )

    # When: 두 등록에 발송한다.
    report = await _sender().send(tokens=tokens, message=message)

    # Then: 등록별 FCM 메시지가 fid로 구성되고 죽은 등록만 보고된다.
    assert report.invalid_fids == ("fid-dead",)
    assert len(sent_batches) == 1
    fcm_messages = cast(list[Any], sent_batches[0])
    assert [fcm_message.fid for fcm_message in fcm_messages] == [
        "fid-live",
        "fid-dead",
    ]
    assert all(fcm_message.notification.title == "혜택 안내" for fcm_message in fcm_messages)
    assert all(
        fcm_message.notification.body == "이번 달 혜택을 확인해 보세요."
        for fcm_message in fcm_messages
    )
    assert all(fcm_message.data == {"kind": "benefit"} for fcm_message in fcm_messages)


async def test_fcm_push_sender_splits_sends_into_batches_of_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: FCM 배치 한도(500)를 넘는 501개 등록이 있다.
    tokens = [
        _push_token(fid=f"fid-{index}", platform=DevicePlatform.ANDROID) for index in range(501)
    ]
    sent_batch_sizes: list[int] = []

    def fake_send_each(
        fcm_messages: list[messaging.Message],
        *,
        app: firebase_admin.App,
    ) -> _FakeBatchResponse:
        sent_batch_sizes.append(len(fcm_messages))
        responses = [_FakeSendResponse(None) for _ in fcm_messages]
        if len(fcm_messages) == 1:
            responses[0] = _FakeSendResponse(messaging.UnregisteredError("죽은 등록"))
        return _FakeBatchResponse(responses)

    monkeypatch.setattr(messaging, "send_each", fake_send_each)

    # When: 전체 등록에 발송한다.
    report = await _sender().send(
        tokens=tokens,
        message=PushMessage(title="혜택 안내", body="본문"),
    )

    # Then: 500개 단위로 나뉘어 호출되고 무효 등록은 배치 전체에서 집계된다.
    assert sent_batch_sizes == [500, 1]
    assert report.invalid_fids == ("fid-500",)


async def test_fcm_push_sender_wraps_batch_failure_as_external_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: FCM 배치 호출 자체가 실패한다.
    def fake_send_each(
        fcm_messages: list[messaging.Message],
        *,
        app: firebase_admin.App,
    ) -> _FakeBatchResponse:
        raise firebase_exceptions.UnavailableError("FCM 연결 실패")

    monkeypatch.setattr(messaging, "send_each", fake_send_each)
    tokens = [_push_token(fid="fid-1", platform=DevicePlatform.ANDROID)]

    # When/Then: ExternalServiceError로 변환되어 전파된다.
    with pytest.raises(ExternalServiceError):
        await _sender().send(
            tokens=tokens,
            message=PushMessage(title="혜택 안내", body="본문"),
        )


async def test_disabled_push_sender_reports_nothing() -> None:
    # Given: 푸시 발송이 꺼진 환경이다.
    sender = DisabledPushSender()
    tokens = [_push_token(fid="fid-1", platform=DevicePlatform.IOS)]

    # When: 발송을 요청한다.
    report = await sender.send(tokens=tokens, message=PushMessage(title="제목", body="본문"))

    # Then: 아무것도 발송하지 않고 빈 보고를 돌려준다.
    assert report.invalid_fids == ()
