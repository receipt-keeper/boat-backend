from collections.abc import Mapping
from datetime import UTC, date, datetime

from app.modules.notifications.domain.schedule_occurrence import ScheduleOccurrenceTargetType
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.notifications.jobs import schedule_push_notifications as scheduler_job
from app.modules.notifications.tests.scheduler_job_builders import (
    CONSENT_USER_ID,
    NO_CONSENT_USER_ID,
    OTHER_RECEIPT_ID,
    RECEIPT_ID,
    activity_candidate,
    consent_settings,
    engagement_rule,
    schedule_command,
    user_candidate,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_fixture import SchedulerFixture


async def test_scheduler_creates_due_warranty_notification_with_device_detail_route() -> None:
    # Given: 09:00에 D-7 보증 캠페인과 영수증 후보가 있다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(),),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 보증 알림 1건과 receipt occurrence 1건이 생성된다.
    assert result.candidates == 1
    assert result.created == 1
    assert result.skipped == 0
    created = fixture.notification_repository.created[0].command
    assert created.kind == "warranty"
    assert created.resource_type == "receipt"
    assert created.resource_id == RECEIPT_ID
    assert created.message == "공기청정기 무상 AS 7일 남았어요."
    assert created.metadata == {"daysUntilExpiry": "7"}
    _assert_no_scheduler_internal_metadata(created.metadata)
    occurrence = next(iter(fixture.occurrence_repository.reserved))
    assert occurrence.campaign_key == "warranty_risk_d7"
    assert occurrence.target_type is ScheduleOccurrenceTargetType.RECEIPT
    assert occurrence.target_id == RECEIPT_ID
    assert occurrence.occurrence_on == date(2026, 7, 9)
    assert fixture.receipt_repository.warranty_queries[0].offset_days == 7


async def test_scheduler_filters_marketing_candidates_without_marketing_consent() -> None:
    # Given: engagement 후보 중 한 명만 marketingConsent=true다.
    fixture = SchedulerFixture(
        rules=(
            engagement_rule(
                campaign_key="engagement_unregistered_receipt_after_7d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
                first_delay_days=7,
                repeat_interval_days=7,
            ),
        ),
        user_candidates=(
            user_candidate(user_id=CONSENT_USER_ID, days_since_joined=7),
            user_candidate(user_id=NO_CONSENT_USER_ID, days_since_joined=7),
        ),
        receipt_activity_candidates=(
            activity_candidate(user_id=CONSENT_USER_ID),
            activity_candidate(user_id=NO_CONSENT_USER_ID),
        ),
        settings=consent_settings(CONSENT_USER_ID),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 동의한 사용자만 home route 마케팅 알림을 받고 내부 route metadata는 남지 않는다.
    assert result.candidates == 2
    assert result.created == 1
    assert result.skipped == 1
    created = fixture.notification_repository.created[0].command
    assert created.user_id == CONSENT_USER_ID
    assert created.kind == "engagement_unregistered_receipt"
    assert created.resource_type is None
    assert created.resource_id is None
    assert created.metadata == {"receiptCount": "0"}
    _assert_no_scheduler_internal_metadata(created.metadata)


async def test_scheduler_dry_run_does_not_write_notifications_or_occurrences() -> None:
    # Given: 생성 가능한 후보가 있다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(),),
    )

    # When: dry-run으로 실행한다.
    result = await fixture.use_case.execute(schedule_command(dry_run=True))

    # Then: 후보는 집계하지만 notification/occurrence/outbox 쓰기는 없다.
    assert result.candidates == 1
    assert result.created == 0
    assert result.skipped == 0
    assert fixture.notification_repository.created == []
    assert fixture.occurrence_repository.reserved == {}


async def test_scheduler_creates_distinct_occurrences_for_distinct_receipts() -> None:
    # Given: 같은 campaign과 occurrence_on을 갖지만 receipt가 다른 후보가 있다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(
            warranty_candidate(receipt_id=RECEIPT_ID),
            warranty_candidate(receipt_id=OTHER_RECEIPT_ID),
        ),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: target_id가 다르므로 별도 occurrence와 알림으로 생성된다.
    assert result.candidates == 2
    assert result.created == 2
    assert {key.target_id for key in fixture.occurrence_repository.reserved} == {
        RECEIPT_ID,
        OTHER_RECEIPT_ID,
    }


def test_scheduler_cli_accepts_explicit_dry_run_false_for_ops_command() -> None:
    # Given: 운영 문서에 고정할 scheduler 명령 인자가 있다.
    argv = (
        "--target-date",
        "2026-07-09",
        "--now",
        "2026-07-09T00:00:00+00:00",
        "--dry-run=false",
    )

    # When: CLI command로 파싱한다.
    command = scheduler_job._parse_command(argv)

    # Then: 명시적인 false가 실제 실행 모드로 해석된다.
    assert command.target_date == date(2026, 7, 9)
    assert command.now == datetime(2026, 7, 9, 0, 0, tzinfo=UTC)
    assert command.dry_run is False


def _assert_no_scheduler_internal_metadata(metadata: Mapping[str, str]) -> None:
    internal_keys = {
        "campaignKey",
        "campaignPolicy",
        "deliveryHistory",
        "occurrenceId",
        "scheduledKey",
        "targetId",
        "targetType",
        "campaign_key",
        "campaign_policy",
        "delivery_history",
        "occurrence_id",
        "scheduled_key",
        "target_id",
        "target_type",
    }
    assert internal_keys.isdisjoint(metadata)
