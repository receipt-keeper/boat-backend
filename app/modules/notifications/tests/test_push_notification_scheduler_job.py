from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.modules.notifications.domain.due_notification import SYSTEM_TIMEZONE
from app.modules.notifications.domain.schedule_occurrence import ScheduleOccurrenceTargetType
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.notifications.jobs import schedule_push_notifications as scheduler_job
from app.modules.notifications.tests.scheduler_job_builders import (
    CONSENT_USER_ID,
    NO_CONSENT_USER_ID,
    OTHER_RECEIPT_ID,
    RECEIPT_ID,
    activity_candidate,
    assert_no_scheduler_internal_metadata,
    consent_settings,
    engagement_rule,
    schedule_command,
    user_candidate,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_fixture import SchedulerFixture
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFact,
)


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
    assert created.kind == "warranty_expiry"
    assert created.resource_type == "receipt"
    assert created.resource_id == RECEIPT_ID
    assert created.message == "공기청정기 무상 AS 7일 남았어요."
    assert created.metadata == {
        "productName": "공기청정기",
        "subCategory": "공기청정기",
    }
    assert_no_scheduler_internal_metadata(created.metadata)
    occurrence = next(iter(fixture.occurrence_repository.reserved))
    assert occurrence.campaign_key == "warranty_risk_d7"
    assert occurrence.target_type is ScheduleOccurrenceTargetType.RECEIPT
    assert occurrence.target_id == RECEIPT_ID
    assert occurrence.occurrence_on == date(2026, 7, 9)
    assert fixture.expiring_receipts_reader.queries[0].offset_days == 7


async def test_scheduler_filters_marketing_candidates_without_marketing_consent() -> None:
    # Given: engagement 후보 중 한 명만 marketingConsent=true다.
    fixture = SchedulerFixture(
        rules=(
            engagement_rule(
                campaign_key="engagement_unregistered_receipt_after_7d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT,
                first_delay_days=7,
                repeat_interval_days=7,
                lookback_days=None,
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
    assert created.kind == "receipt_registration_reminder"
    assert created.resource_type is None
    assert created.resource_id is None
    assert created.metadata == {"receiptCount": "0"}
    assert_no_scheduler_internal_metadata(created.metadata)
    assert fixture.receipt_activity_reader.queries[0].recent_since is None
    assert set(fixture.notification_repository.settings_for_update_calls) == {
        CONSENT_USER_ID,
        NO_CONSENT_USER_ID,
    }


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


async def test_scheduler_filters_rules_by_campaign_key() -> None:
    # Given: 서로 다른 D-day 규칙과 각각의 만료 예정 영수증이 있다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(campaign_key="warranty_d7", day_offset=7),
            warranty_rule(campaign_key="warranty_d10", day_offset=10),
        ),
        warranty_candidates=(
            warranty_candidate(receipt_id=RECEIPT_ID),
            warranty_candidate(
                receipt_id=OTHER_RECEIPT_ID,
                expires_on=date(2026, 7, 19),
            ),
        ),
    )

    # When: 특정 campaign key만 지정해 실행한다.
    result = await fixture.use_case.execute(schedule_command(campaign_key="warranty_d10"))

    # Then: 대상 규칙과 영수증만 집계 및 생성한다.
    assert tuple(summary.campaign_key for summary in result.rules) == ("warranty_d10",)
    assert result.created == 1
    assert fixture.notification_repository.created[0].command.resource_id == OTHER_RECEIPT_ID


async def test_scheduler_iterates_multiple_warranty_and_user_fact_pages() -> None:
    # Given: batch size보다 많은 warranty와 가입 사실 후보가 있다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(campaign_key="warranty_d7", day_offset=7),
            engagement_rule(
                campaign_key="engagement_all_users_14d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
                first_delay_days=14,
                repeat_interval_days=14,
            ),
        ),
        warranty_candidates=(
            warranty_candidate(receipt_id=RECEIPT_ID),
            warranty_candidate(receipt_id=OTHER_RECEIPT_ID),
        ),
        user_candidates=(
            user_candidate(user_id=CONSENT_USER_ID, days_since_joined=14),
            user_candidate(user_id=NO_CONSENT_USER_ID, days_since_joined=14),
        ),
        settings=consent_settings(CONSENT_USER_ID, NO_CONSENT_USER_ID),
    )

    # When: 한 건씩 page를 읽도록 실행한다.
    result = await fixture.use_case.execute(schedule_command(batch_size=1))

    # Then: warranty와 users query가 모두 다음 page까지 순회한다.
    assert result.created == 4
    assert len(fixture.expiring_receipts_reader.queries) == 2
    assert len(fixture.user_registration_facts_reader.queries) == 2


async def test_scheduler_skips_withdrawn_warranty_owner_without_stopping_pagination() -> None:
    withdrawn_user_id = UUID("00000000-0000-0000-0000-000000000901")
    active_user_id = UUID("00000000-0000-0000-0000-000000000902")
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_d7", day_offset=7),),
        warranty_candidates=(
            warranty_candidate(user_id=withdrawn_user_id, receipt_id=RECEIPT_ID),
            warranty_candidate(user_id=active_user_id, receipt_id=OTHER_RECEIPT_ID),
        ),
        existing_user_ids=frozenset({active_user_id}),
    )

    result = await fixture.use_case.execute(schedule_command(batch_size=1))

    assert result.candidates == 1
    assert result.created == 1
    assert fixture.notification_repository.created[0].command.user_id == active_user_id
    assert [query.user_ids for query in fixture.existing_user_ids_reader.queries] == [
        (withdrawn_user_id,),
        (active_user_id,),
    ]


async def test_scheduler_uses_scheduled_cutoff_for_historical_and_late_current_day_warranty() -> (
    None
):
    target_date = date(2026, 7, 9)
    scheduled_cutoff = datetime(2026, 7, 9, 0, 0, tzinfo=UTC)
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_d7", day_offset=7),),
        warranty_candidates=(
            warranty_candidate(created_at=scheduled_cutoff),
            warranty_candidate(
                receipt_id=OTHER_RECEIPT_ID,
                created_at=scheduled_cutoff + timedelta(minutes=1),
            ),
        ),
    )

    historical = await fixture.use_case.execute(
        schedule_command(target_date=target_date, now=datetime(2026, 7, 10, 0, 0, tzinfo=UTC))
    )
    late_current_day = await fixture.fresh_use_case().execute(
        schedule_command(target_date=target_date, now=datetime(2026, 7, 9, 9, 0, tzinfo=UTC))
    )

    assert historical.candidates == 0
    assert late_current_day.candidates == 0
    assert [query.observed_before for query in fixture.expiring_receipts_reader.queries] == [
        scheduled_cutoff,
        scheduled_cutoff,
    ]


async def test_scheduler_uses_scheduled_cutoff_for_registration_and_activity_facts() -> None:
    target_date = date(2026, 7, 9)
    scheduled_cutoff = datetime(2026, 7, 9, 0, 0, tzinfo=UTC)
    fixture = SchedulerFixture(
        rules=(
            engagement_rule(
                campaign_key="engagement_inactive_receipt_7d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
                first_delay_days=None,
                repeat_interval_days=7,
                lookback_days=7,
            ),
        ),
        user_candidates=(
            user_candidate(user_id=CONSENT_USER_ID, days_since_joined=7),
            UserRegistrationFact(user_id=NO_CONSENT_USER_ID, registered_at=scheduled_cutoff),
        ),
        receipt_activity_candidates=(
            activity_candidate(
                user_id=CONSENT_USER_ID,
                receipt_count=1,
                last_receipt_created_at=datetime(2026, 7, 1, 14, 59, tzinfo=UTC),
            ),
        ),
        settings=consent_settings(CONSENT_USER_ID),
    )

    result = await fixture.use_case.execute(
        schedule_command(target_date=target_date, now=datetime(2026, 7, 10, 0, 0, tzinfo=UTC))
    )

    assert result.created == 1
    assert fixture.user_registration_facts_reader.queries[0].observed_before == scheduled_cutoff
    assert fixture.receipt_activity_reader.queries[0].observed_before == scheduled_cutoff


async def test_scheduler_creates_inactive_receipt_reminder_with_receipt_count() -> None:
    # Given: 최근 영수증이 없는 가입 7일 사용자와 기존 영수증 활동 사실이 있다.
    fixture = SchedulerFixture(
        rules=(
            engagement_rule(
                campaign_key="engagement_inactive_receipt_7d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT,
                first_delay_days=None,
                repeat_interval_days=7,
                lookback_days=7,
            ),
        ),
        user_candidates=(user_candidate(user_id=CONSENT_USER_ID, days_since_joined=7),),
        receipt_activity_candidates=(activity_candidate(user_id=CONSENT_USER_ID, receipt_count=3),),
        settings=consent_settings(CONSENT_USER_ID),
    )

    # When: due notifications를 생성한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: inactive delivery contract와 receiptCount metadata를 보존한다.
    assert result.created == 1
    created = fixture.notification_repository.created[0].command
    assert created.kind == "receipt_inactivity_reminder"
    assert created.metadata == {"receiptCount": "3"}
    assert fixture.receipt_activity_reader.queries[0].recent_since == datetime(
        2026, 7, 2, 0, 0, tzinfo=SYSTEM_TIMEZONE
    )


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
