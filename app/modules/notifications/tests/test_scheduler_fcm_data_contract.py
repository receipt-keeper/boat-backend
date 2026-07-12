from datetime import UTC, date, datetime
from typing import assert_never
from uuid import UUID

import firebase_admin
import pytest
from firebase_admin import messaging

from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
)
from app.modules.notifications.application.commands.send_notification_push.use_case import (
    SendNotificationPushCommandUseCase,
)
from app.modules.notifications.application.due_notification import (
    DueNotification,
    receipt_reminder_notification,
    warranty_expiry_notification,
)
from app.modules.notifications.domain.due_notification import (
    DueNotificationRule,
    resolve_due_notification_rule,
)
from app.modules.notifications.domain.model import NotificationSettings
from app.modules.notifications.domain.schedule_rule import (
    NotificationScheduleRule,
    ScheduleRuleTargetKind,
)
from app.modules.notifications.domain.value_objects import DevicePlatform
from app.modules.notifications.infrastructure.fcm.push_sender import FcmPushSender
from app.modules.notifications.tests.scheduler_job_builders import (
    CONSENT_USER_ID,
    engagement_rule,
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
    scheduled = _due_notification(target_kind)

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
    scheduled = _due_notification(target_kind)

    # When: 공용 발송 경로에서 실제 FCM 메시지를 만든다.
    data = await _send_to_fcm(
        monkeypatch=monkeypatch,
        scheduled=scheduled,
        kind=legacy_kind,
    )

    # Then: 외부 앱에는 새 kind 계약만 노출된다.
    assert data["kind"] == expected_kind


def _due_notification(
    target_kind: ScheduleRuleTargetKind,
) -> DueNotification:
    match target_kind:
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
            candidate = warranty_candidate()
            return warranty_expiry_notification(
                due_rule=_due_rule(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7)),
                user_id=CONSENT_USER_ID,
                receipt_id=candidate.receipt_id,
                item_name=candidate.item_name,
                sub_category=candidate.sub_category,
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
    return receipt_reminder_notification(
        due_rule=_due_rule(rule),
        user_id=CONSENT_USER_ID,
    )


def _due_rule(rule: NotificationScheduleRule) -> DueNotificationRule:
    due_rule = resolve_due_notification_rule(
        rule=rule,
        now=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        target_date=OCCURRENCE_ON,
    )
    assert due_rule is not None
    return due_rule


async def _send_to_fcm(
    *,
    monkeypatch: pytest.MonkeyPatch,
    scheduled: DueNotification,
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
