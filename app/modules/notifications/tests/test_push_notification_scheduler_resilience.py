from app.modules.notifications.tests.scheduler_job_builders import (
    OTHER_RECEIPT_ID,
    schedule_command,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_fixture import SchedulerFixture


async def test_scheduler_isolates_rendered_validation_error_per_candidate() -> None:
    # Given: 첫 후보는 렌더링 후 message 길이 검증에 실패하고 두 번째 후보는 정상이다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(
            warranty_candidate(item_name="가" * 260),
            warranty_candidate(receipt_id=OTHER_RECEIPT_ID),
        ),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 실패 후보만 failed로 집계하고 정상 후보의 occurrence/notification은 생성된다.
    assert result.candidates == 2
    assert result.failed == 1
    assert result.created == 1
    assert len(fixture.notification_repository.created) == 1
    assert fixture.notification_repository.created[0].command.resource_id == OTHER_RECEIPT_ID
    assert len(fixture.occurrence_repository.reserved) == 1
    occurrence = next(iter(fixture.occurrence_repository.reserved))
    assert occurrence.target_id == OTHER_RECEIPT_ID
    assert fixture.unit_of_work.rollbacks == 1
