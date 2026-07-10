from datetime import time

from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.notifications.tests.scheduler_job_builders import (
    CONSENT_USER_ID,
    consent_settings,
    engagement_rule,
    schedule_command,
    user_candidate,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_fixture import SchedulerFixture


async def test_scheduler_disabled_rule_and_no_candidate_are_noops() -> None:
    # Given: 비활성 rule과 후보 없는 활성 rule이 있다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(campaign_key="disabled", day_offset=7, enabled=False),
            warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),
        )
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 조회 가능한 후보가 없어 쓰기 없이 종료한다.
    assert result.candidates == 0
    assert result.created == 0
    assert result.skipped == 0
    assert fixture.notification_repository.created == []
    assert fixture.occurrence_repository.reserved == {}


async def test_scheduler_is_idempotent_on_second_run_by_occurrence() -> None:
    # Given: 같은 후보를 반환하는 fresh process 스타일 use case를 두 번 조립한다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(),),
    )

    # When: scheduler를 두 번 실행한다.
    first = await fixture.use_case.execute(schedule_command())
    second = await fixture.fresh_use_case().execute(schedule_command())

    # Then: 첫 실행만 생성되고 두 번째는 occurrence 중복으로 skip된다.
    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1
    assert len(fixture.notification_repository.created) == 1
    assert len(fixture.occurrence_repository.reserved) == 1


async def test_scheduler_rule_copy_or_send_time_change_does_not_bypass_same_occurrence() -> None:
    # Given: 한 번 생성된 warranty occurrence가 있다.
    fixture = SchedulerFixture(
        rules=(
            warranty_rule(
                campaign_key="warranty_risk_d7",
                day_offset=7,
                body_template="[기기명] 첫 문구",
            ),
        ),
        warranty_candidates=(warranty_candidate(),),
    )
    first = await fixture.use_case.execute(schedule_command())
    await fixture.schedule_rule_repository.upsert_many(
        rules=(
            warranty_rule(
                campaign_key="warranty_risk_d7",
                day_offset=7,
                send_time_local=time(8, 0),
                body_template="[기기명] 바뀐 문구",
            ),
        )
    )

    # When: 같은 business occurrence로 다시 실행한다.
    second = await fixture.fresh_use_case().execute(schedule_command())

    # Then: copy/send time 변경은 같은 occurrence 중복을 우회하지 않는다.
    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1
    assert len(fixture.notification_repository.created) == 1


async def test_scheduler_rolls_back_reserved_occurrence_on_handled_create_failure() -> None:
    # Given: notification create/publish 단계가 typed failure를 던지도록 주입한다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(),),
        fail_creates=True,
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 실패로 집계하고 rollback을 호출한다.
    assert result.candidates == 1
    assert result.created == 0
    assert result.failed == 1
    assert fixture.unit_of_work.rollbacks == 1


async def test_scheduler_still_gates_engagement_by_marketing_consent() -> None:
    # Given: consent가 없는 engagement 후보가 있다.
    fixture = SchedulerFixture(
        rules=(
            engagement_rule(
                campaign_key="engagement_all_users_14d",
                target_kind=ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER,
                first_delay_days=14,
                repeat_interval_days=14,
            ),
        ),
        user_candidates=(user_candidate(user_id=CONSENT_USER_ID, days_since_joined=14),),
        settings=consent_settings(),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 마케팅 수신 동의가 없으면 occurrence도 예약하지 않는다.
    assert result.candidates == 1
    assert result.created == 0
    assert result.skipped == 1
    assert fixture.occurrence_repository.reserved == {}
