from datetime import date
from typing import assert_never
from uuid import UUID

import firebase_admin
import pytest
from firebase_admin import messaging

from app.modules.notifications.application.commands.schedule_push_notifications import (
    candidate_factory,
    scheduler_models,
)
from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
)
from app.modules.notifications.application.commands.send_notification_push.use_case import (
    SendNotificationPushCommandUseCase,
)
from app.modules.notifications.domain.model import NotificationSettings
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.notifications.domain.value_objects import DevicePlatform
from app.modules.notifications.infrastructure.fcm.push_sender import FcmPushSender
from app.modules.notifications.tests.scheduler_job_builders import (
    CONSENT_USER_ID,
    engagement_rule,
    user_candidate,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.test_application import (
    InMemoryNotificationRepository,
    InMemoryPushTokenRepository,
)
from tests.support.unit_of_work import FakeUnitOfWork

NOTIFICATION_ID = UUID("00000000-0000-0000-0000-000000000301")
OCCURRENCE_ON = date(2026, 7, 9)


class _FakeSendResponse:
    exception: None = None


class _FakeBatchResponse:
    def __init__(self, count: int) -> None:
        self.responses = [_FakeSendResponse() for _ in range(count)]


@pytest.mark.parametrize(
    ("target_kind", "expected_data"),
    [
        (
            ScheduleRuleTargetKind.WARRANTY_RECEIPT,
            {
                "notificationId": str(NOTIFICATION_ID),
                "messageType": "transactional",
                "kind": "warranty_expiry",
                "resourceType": "receipt",
                "resourceId": "00000000-0000-0000-0000-000000000201",
            },
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
            {
                "notificationId": str(NOTIFICATION_ID),
                "messageType": "marketing",
                "kind": "receipt_registration_reminder",
            },
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
            {
                "notificationId": str(NOTIFICATION_ID),
                "messageType": "marketing",
                "kind": "receipt_inactivity_reminder",
            },
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
            {
                "notificationId": str(NOTIFICATION_ID),
                "messageType": "marketing",
                "kind": "receipt_analysis_reminder",
            },
        ),
    ],
)
async def test_scheduler_notification_uses_shared_fcm_data_contract(
    monkeypatch: pytest.MonkeyPatch,
    target_kind: ScheduleRuleTargetKind,
    expected_data: dict[str, str],
) -> None:
    # Given: 스케줄러가 만든 알림 후보와 FCM 등록 토큰이 있다.
    scheduled = _schedule_candidate(target_kind)

    # When: 생성 이벤트에서 전달될 값으로 FCM 푸시를 발송한다.
    data = await _send_to_fcm(monkeypatch=monkeypatch, scheduled=scheduled)

    # Then: 앱에 공유한 키만 FCM data에 포함된다.
    assert data == expected_data


@pytest.mark.parametrize(
    ("target_kind", "legacy_kind", "expected_kind"),
    [
        (ScheduleRuleTargetKind.WARRANTY_RECEIPT, "warranty", "warranty_expiry"),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
            "engagement_unregistered_receipt",
            "receipt_registration_reminder",
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
            "engagement_inactive_receipt",
            "receipt_inactivity_reminder",
        ),
        (
            ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
            "engagement_all_user",
            "receipt_analysis_reminder",
        ),
    ],
)
async def test_legacy_scheduler_kind_is_normalized_at_fcm_boundary(
    monkeypatch: pytest.MonkeyPatch,
    target_kind: ScheduleRuleTargetKind,
    legacy_kind: str,
    expected_kind: str,
) -> None:
    # Given: 배포 전 이벤트가 구 scheduler kind를 가지고 있다.
    scheduled = _schedule_candidate(target_kind)

    # When: 공용 발송 경로에서 실제 FCM 메시지를 만든다.
    data = await _send_to_fcm(
        monkeypatch=monkeypatch,
        scheduled=scheduled,
        kind=legacy_kind,
    )

    # Then: 외부 앱에는 새 kind 계약만 노출된다.
    assert data["kind"] == expected_kind


def _schedule_candidate(
    target_kind: ScheduleRuleTargetKind,
) -> scheduler_models.ScheduleCandidate:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            return candidate_factory.warranty_schedule_candidate(
                rule=warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),
                candidate=warranty_candidate(),
                occurrence_on=OCCURRENCE_ON,
            )
        case ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT:
            rule = engagement_rule(
                campaign_key="engagement_unregistered_receipt_after_7d",
                target_kind=target_kind,
                first_delay_days=7,
                repeat_interval_days=7,
                lookback_days=None,
            )
        case ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT:
            rule = engagement_rule(
                campaign_key="engagement_inactive_receipt_7d",
                target_kind=target_kind,
                first_delay_days=None,
                repeat_interval_days=7,
                lookback_days=7,
            )
        case ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
            rule = engagement_rule(
                campaign_key="engagement_all_users_14d",
                target_kind=target_kind,
                first_delay_days=14,
                repeat_interval_days=14,
                lookback_days=None,
            )
        case unreachable:
            assert_never(unreachable)

    return candidate_factory.engagement_schedule_candidate(
        rule=rule,
        candidate=user_candidate(user_id=CONSENT_USER_ID, days_since_joined=14),
        bucket_on=OCCURRENCE_ON,
    )


async def _send_to_fcm(
    *,
    monkeypatch: pytest.MonkeyPatch,
    scheduled: scheduler_models.ScheduleCandidate,
    kind: str | None = None,
) -> dict[str, str]:
    notification_repository = InMemoryNotificationRepository()
    notification_repository.settings[scheduled.command.user_id] = NotificationSettings.create(
        user_id=scheduled.command.user_id,
        marketing_consent=True,
    )
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=scheduled.command.user_id,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    sent_messages: list[messaging.Message] = []

    def fake_send_each(
        messages: list[messaging.Message],
        *,
        app: firebase_admin.App,
    ) -> _FakeBatchResponse:
        sent_messages.extend(messages)
        return _FakeBatchResponse(len(messages))

    monkeypatch.setattr(messaging, "send_each", fake_send_each)
    use_case = SendNotificationPushCommandUseCase(
        notification_repository=notification_repository,
        push_token_repository=push_token_repository,
        push_sender=FcmPushSender(app=firebase_admin.App.__new__(firebase_admin.App)),
        unit_of_work=FakeUnitOfWork(),
    )
    await use_case.execute(
        SendNotificationPushCommand(
            user_id=scheduled.command.user_id,
            notification_id=NOTIFICATION_ID,
            message_type=scheduled.command.message_type,
            kind=scheduled.command.kind if kind is None else kind,
            title=scheduled.command.title,
            message=scheduled.command.message,
            resource_type=scheduled.command.resource_type,
            resource_id=scheduled.command.resource_id,
        )
    )
    assert len(sent_messages) == 1
    return sent_messages[0].data or {}
