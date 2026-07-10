from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.modules.notifications.application.commands.schedule_push_notifications import (
    schedule_rule_due,
)
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.notifications.tests.scheduler_job_builders import (
    CONSENT_USER_ID,
    FOURTEEN_DAY_USER_ID,
    consent_settings,
    engagement_rule,
    schedule_command,
    user_candidate,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_fixture import SchedulerFixture


async def test_scheduler_waits_until_rule_send_time() -> None:
    # Given: 현 now보다 늦은 send_time_local을 가진 rule이 있다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(
                campaign_key="warranty_risk_d7",
                day_offset=7,
                send_time_local=time(10, 0),
            ),
        ),
        warranty_candidates=(warranty_candidate(),),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(
        schedule_command(now=datetime(2026, 7, 9, 0, 0, tzinfo=UTC))
    )

    # Then: 해당 rule은 due가 아니므로 후보 조회와 쓰기가 없다.
    assert result.candidates == 0
    assert result.created == 0
    assert fixture.receipt_repository.warranty_queries == []
    assert fixture.notification_repository.created == []
    assert fixture.occurrence_repository.reserved == {}


async def test_scheduler_uses_mutable_rule_offset_join_delay_and_repeat_data() -> None:
    # Given: rule 데이터가 비 PM D-10과 가입 10일 반복 캠페인을 가리킨다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(campaign_key="warranty_custom_d10", day_offset=10),
            engagement_rule(
                campaign_key="engagement_all_users_10d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
                first_delay_days=10,
                repeat_interval_days=10,
            ),
        ),
        warranty_candidates=(
            warranty_candidate(
                expires_on=date(2026, 7, 19),
                days_until_expiry=10,
                item_name="노트북",
            ),
        ),
        user_candidates=(
            user_candidate(
                user_id=CONSENT_USER_ID,
                days_since_joined=10,
            ),
        ),
        settings=consent_settings(CONSENT_USER_ID),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: rule offset/join-delay/repeat 기준으로 두 캠페인이 생성된다.
    assert result.candidates == 2
    assert result.created == 2
    assert fixture.receipt_repository.warranty_queries[0].offset_days == 10
    commands = [created.command for created in fixture.notification_repository.created]
    assert [command.kind for command in commands] == ["warranty", "engagement_all_user"]
    assert [command.metadata for command in commands] == [{"daysUntilExpiry": "10"}, {}]
    for command in commands:
        _assert_no_scheduler_internal_metadata(command.metadata)


async def test_scheduler_creates_new_warranty_occurrence_when_policy_offset_changes_due_date() -> (
    None
):
    # Given: 같은 receipt/campaign이 D-7 due date에 이미 발송됐다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk", day_offset=7),),
        warranty_candidates=(warranty_candidate(expires_on=date(2026, 7, 16)),),
    )
    first = await fixture.use_case.execute(
        schedule_command(
            target_date=date(2026, 7, 9),
            now=datetime(2026, 7, 9, 9, 0, tzinfo=UTC),
        )
    )
    await fixture.schedule_rule_repository.upsert_many(
        rules=(warranty_rule(campaign_key="warranty_risk", day_offset=10),)
    )

    # When: 같은 receipt/campaign이 D-10 due date로 다시 due가 된다.
    second = await fixture.fresh_use_case().execute(
        schedule_command(
            target_date=date(2026, 7, 6),
            now=datetime(2026, 7, 6, 9, 0, tzinfo=UTC),
        )
    )

    # Then: expires_on이 같아도 due business date가 다르므로 occurrence와 알림이 각각 생성된다.
    assert first.created == 1
    assert second.created == 1
    assert len(fixture.notification_repository.created) == 2
    assert {occurrence.occurrence_on for occurrence in fixture.occurrence_repository.reserved} == {
        date(2026, 7, 6),
        date(2026, 7, 9),
    }


async def test_scheduler_allows_historical_target_date_without_matching_now() -> None:
    # Given: target_date는 과거 KST 영업일이고 현재 clock은 다음 날이다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(expires_on=date(2026, 7, 16)),),
    )

    # When: now를 target_date에 맞추지 않고 backfill 실행한다.
    result = await fixture.use_case.execute(
        schedule_command(
            target_date=date(2026, 7, 9),
            now=datetime(2026, 7, 10, 0, 0, tzinfo=UTC),
        )
    )

    # Then: historical backfill은 현재 send_time과 무관하게 due다.
    assert result.created == 1
    assert fixture.receipt_repository.warranty_queries[0].target_date == date(2026, 7, 9)


async def test_scheduler_uses_kst_midnight_for_current_target_date() -> None:
    # Given: UTC 7/8 15:00은 KST 7/9 00:00이고 rule도 00:00 발송이다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(
                campaign_key="warranty_risk_d7",
                day_offset=7,
                send_time_local=time(0, 0),
            ),
        ),
        warranty_candidates=(warranty_candidate(expires_on=date(2026, 7, 16)),),
    )

    # When: explicit target_date 없이 현재 KST 날짜 기준으로 실행한다.
    result = await fixture.use_case.execute(
        schedule_command(target_date=None, now=datetime(2026, 7, 8, 15, 0, tzinfo=UTC))
    )

    # Then: UTC 날짜가 아니라 KST 날짜인 7/9가 스캔된다.
    assert result.created == 1
    assert fixture.receipt_repository.warranty_queries[0].target_date == date(2026, 7, 9)


async def test_scheduler_future_target_date_is_noop() -> None:
    # Given: 현재 KST 날짜보다 미래 target_date가 들어왔다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(expires_on=date(2026, 7, 17)),),
    )

    # When: 미래 target_date로 실행한다.
    result = await fixture.use_case.execute(
        schedule_command(
            target_date=date(2026, 7, 10),
            now=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        )
    )

    # Then: 미래 backfill은 실행하지 않는다.
    assert result.created == 0
    assert fixture.receipt_repository.warranty_queries == []


async def test_scheduler_enforces_send_time_for_today_in_kst() -> None:
    # Given: 오늘 KST 09:00 발송 rule과 오늘 due 후보가 있다.
    rule = warranty_rule(
        campaign_key="warranty_risk_d7",
        day_offset=7,
        send_time_local=time(9, 0),
    )
    before_fixture = SchedulerFixture(
        rules=(rule,),
        warranty_candidates=(warranty_candidate(expires_on=date(2026, 7, 16)),),
    )
    after_fixture = SchedulerFixture(
        rules=(rule,),
        warranty_candidates=(warranty_candidate(expires_on=date(2026, 7, 16)),),
    )

    # When: KST 08:59와 09:00에 각각 실행한다.
    before = await before_fixture.use_case.execute(
        schedule_command(
            target_date=date(2026, 7, 9),
            now=datetime(2026, 7, 8, 23, 59, tzinfo=UTC),
        )
    )
    after = await after_fixture.use_case.execute(
        schedule_command(
            target_date=date(2026, 7, 9),
            now=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        )
    )

    # Then: 오늘 KST는 send_time_local 전에는 no-op, 이후에는 due다.
    assert before.created == 0
    assert before_fixture.receipt_repository.warranty_queries == []
    assert after.created == 1
    assert after_fixture.receipt_repository.warranty_queries[0].target_date == date(2026, 7, 9)


def test_due_schedule_rule_builds_kst_scheduled_for() -> None:
    # Given: KST 시스템 send_time rule이 있다.
    rule = warranty_rule(campaign_key="warranty_risk_d7", day_offset=7)
    command = schedule_command(
        target_date=date(2026, 7, 9),
        now=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
    )

    # When: due rule을 계산한다.
    due_rule = schedule_rule_due.due_schedule_rule(rule=rule, command=command)

    # Then: scheduled_for는 rule의 KST local send time을 가진 aware datetime이다.
    assert due_rule is not None
    assert due_rule.scheduled_for == datetime(
        2026,
        7,
        9,
        9,
        0,
        tzinfo=ZoneInfo("Asia/Seoul"),
    )


async def test_scheduler_uses_21_day_rule_cadence_without_user_bucket_code_change() -> None:
    # Given: users provider는 가입일 사실만 주고 rule이 21일 반복 주기를 가진다.
    fixture = SchedulerFixture(
        rules=(
            engagement_rule(
                campaign_key="engagement_all_users_21d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
                first_delay_days=21,
                repeat_interval_days=21,
            ),
        ),
        user_candidates=(
            user_candidate(
                user_id=FOURTEEN_DAY_USER_ID,
                days_since_joined=21,
            ),
        ),
        settings=consent_settings(FOURTEEN_DAY_USER_ID),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 7/14 전용 bucket 없이도 21일 주기 캠페인이 생성된다.
    assert result.candidates == 1
    assert result.created == 1
    created = fixture.notification_repository.created[0].command
    assert created.kind == "engagement_all_user"
    assert created.metadata == {}


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
