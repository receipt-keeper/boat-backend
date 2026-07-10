import pytest

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.notifications.tests.scheduler_job_builders import (
    OTHER_RECEIPT_ID,
    RECEIPT_ID,
    schedule_command,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_fixture import SchedulerFixture


async def test_scheduler_creates_notifications_for_long_rendered_item_names() -> None:
    # Given: 첫 후보는 긴 품목명이고 두 번째 후보는 정상 품목명이다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(
            warranty_candidate(item_name="가" * 260),
            warranty_candidate(receipt_id=OTHER_RECEIPT_ID),
        ),
    )

    # When: scheduler를 실행한다.
    result = await fixture.use_case.execute(schedule_command())

    # Then: 두 품목명 모두 유효 길이로 렌더링되어 occurrence/notification이 생성된다.
    assert result.candidates == 2
    assert result.failed == 0
    assert result.created == 2
    assert len(fixture.notification_repository.created) == 2
    assert {created.command.resource_id for created in fixture.notification_repository.created} == {
        RECEIPT_ID,
        OTHER_RECEIPT_ID,
    }
    assert len(fixture.occurrence_repository.reserved) == 2
    assert fixture.unit_of_work.rollbacks == 0


async def test_scheduler_isolates_validation_error_and_continues_next_candidate() -> None:
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(
            warranty_candidate(),
            warranty_candidate(receipt_id=OTHER_RECEIPT_ID),
        ),
        notification_create_exceptions=[
            ValidationError([ErrorDetail(field="message", message="invalid")]),
            None,
        ],
    )

    result = await fixture.use_case.execute(schedule_command())

    assert result.candidates == 2
    assert result.failed == 1
    assert result.created == 1
    assert len(fixture.notification_repository.created) == 1
    assert fixture.notification_repository.created[0].command.resource_id == OTHER_RECEIPT_ID
    assert len(fixture.occurrence_repository.reserved) == 1
    assert next(iter(fixture.occurrence_repository.reserved)).target_id == OTHER_RECEIPT_ID
    assert fixture.unit_of_work.rollbacks == 1


async def test_scheduler_rolls_back_and_reraises_unexpected_creation_error() -> None:
    # Given: notification persistence가 unexpected RuntimeError로 실패한다.
    fixture = SchedulerFixture(
        rules=(warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),),
        warranty_candidates=(warranty_candidate(),),
        notification_create_exception=RuntimeError("outbox unavailable"),
    )

    # When/Then: 잡은 transaction을 rollback하고 성공처럼 집계하지 않는다.
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await fixture.use_case.execute(schedule_command())

    assert fixture.unit_of_work.rollbacks == 1
    assert fixture.occurrence_repository.reserved == {}
