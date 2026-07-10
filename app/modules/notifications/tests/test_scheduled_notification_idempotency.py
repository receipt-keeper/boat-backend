from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
    NotificationCreator,
)
from app.modules.notifications.application.commands.schedule_push_notifications.command import (
    SchedulePushNotificationsCommand,
)
from app.modules.notifications.application.commands.schedule_push_notifications.use_case import (
    SchedulePushNotificationsCommandUseCase,
)
from app.modules.notifications.dependencies import build_notification_event_registry
from app.modules.notifications.domain.value_objects import NotificationMessageType
from app.modules.notifications.infrastructure.persistence.orm import UserNotification
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyScheduleOccurrenceRepository,
)
from app.modules.notifications.infrastructure.persistence.schedule_occurrence_orm import (
    NotificationScheduleOccurrence,
)
from app.modules.notifications.tests.scheduler_job_builders import (
    NOW,
    RECEIPT_ID,
    TARGET_DATE,
    warranty_candidate,
    warranty_rule,
)
from app.modules.notifications.tests.scheduler_job_candidate_repositories import (
    ReceiptRepositoryFake,
    UserRepositoryFake,
)
from app.modules.notifications.tests.scheduler_job_fixture import FailingNotificationCreator
from app.modules.notifications.tests.scheduler_job_occurrence_repositories import (
    ScheduleRuleRepositoryFake,
)
from app.modules.receipts.application.ports.receipt_repository import WarrantyNotificationCandidate

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
CREATED_AT = datetime(2026, 7, 9, 9, 0, 0, tzinfo=UTC)


async def test_ad_hoc_notifications_remain_repeatable(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    receipt_id = uuid4()

    async with postgres_session_factory() as session:
        use_case = _ad_hoc_use_case(session)
        first = await use_case.execute(_ad_hoc_command(receipt_id=receipt_id))
        second = await use_case.execute(_ad_hoc_command(receipt_id=receipt_id))

    async with postgres_session_factory() as session:
        assert first.notification_id != second.notification_id
        assert await _notification_count(session) == 2
        assert await _outbox_count(session) == 2
        assert await _occurrence_count(session) == 0


async def test_identical_scheduler_run_creates_one_occurrence_notification_and_outbox(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    candidate = warranty_candidate(receipt_id=RECEIPT_ID)

    async with postgres_session_factory() as session:
        first = await _scheduler_use_case(session, candidates=(candidate,)).execute(
            _schedule_command(TARGET_DATE)
        )
    async with postgres_session_factory() as session:
        second = await _scheduler_use_case(session, candidates=(candidate,)).execute(
            _schedule_command(TARGET_DATE)
        )

    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1
    async with postgres_session_factory() as session:
        assert await _notification_count(session) == 1
        assert await _outbox_count(session) == 1
        assert await _occurrence_count(session) == 1
        assert await _occurrence_key_rows(session) == (
            ("warranty_risk_d7", "receipt", RECEIPT_ID, date(2026, 7, 9)),
        )


async def test_different_occurrence_date_creates_distinct_scheduler_notification(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_candidate = warranty_candidate(receipt_id=RECEIPT_ID, expires_on=date(2026, 7, 16))
    second_candidate = warranty_candidate(receipt_id=RECEIPT_ID, expires_on=date(2026, 7, 17))

    async with postgres_session_factory() as session:
        await _scheduler_use_case(session, candidates=(first_candidate,)).execute(
            _schedule_command(date(2026, 7, 9))
        )
    async with postgres_session_factory() as session:
        await _scheduler_use_case(session, candidates=(second_candidate,)).execute(
            _schedule_command(date(2026, 7, 10))
        )

    async with postgres_session_factory() as session:
        assert await _notification_count(session) == 2
        assert await _outbox_count(session) == 2
        assert await _occurrence_count(session) == 2


async def test_handled_create_failure_rolls_back_occurrence_notification_and_outbox(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        result = await _scheduler_use_case(
            session,
            candidates=(warranty_candidate(),),
            fail_creates=True,
        ).execute(_schedule_command(TARGET_DATE))

    assert result.failed == 1
    async with postgres_session_factory() as session:
        assert await _notification_count(session) == 0
        assert await _outbox_count(session) == 0
        assert await _occurrence_count(session) == 0


def _scheduler_use_case(
    session: AsyncSession,
    *,
    candidates: tuple[WarrantyNotificationCandidate, ...],
    fail_creates: bool = False,
) -> SchedulePushNotificationsCommandUseCase:
    notification_repository = SqlAlchemyNotificationRepository(session)
    event_publisher = OutboxEventPublisher(
        session=session,
        registry=build_notification_event_registry(),
    )
    notification_creator = (
        FailingNotificationCreator()
        if fail_creates
        else NotificationCreator(
            notification_repository=notification_repository,
            event_publisher=event_publisher,
            clock=lambda: CREATED_AT,
        )
    )
    return SchedulePushNotificationsCommandUseCase(
        schedule_rule_repository=ScheduleRuleRepositoryFake(
            (warranty_rule(campaign_key="warranty_risk_d7", day_offset=7),)
        ),
        occurrence_repository=SqlAlchemyScheduleOccurrenceRepository(session),
        notification_repository=notification_repository,
        receipt_repository=ReceiptRepositoryFake(
            warranty_candidates=candidates,
            receipt_activity_candidates=(),
        ),
        user_repository=UserRepositoryFake(()),
        notification_creator=notification_creator,
        unit_of_work=SqlAlchemyUnitOfWork(session),
    )


def _schedule_command(target_date: date) -> SchedulePushNotificationsCommand:
    return SchedulePushNotificationsCommand(
        target_date=target_date,
        now=NOW.replace(year=target_date.year, month=target_date.month, day=target_date.day),
        campaign_key=None,
        dry_run=False,
        batch_size=10,
    )


def _ad_hoc_use_case(session: AsyncSession) -> CreateNotificationCommandUseCase:
    return CreateNotificationCommandUseCase(
        notification_repository=SqlAlchemyNotificationRepository(session),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=OutboxEventPublisher(
            session=session,
            registry=build_notification_event_registry(),
        ),
        clock=lambda: CREATED_AT,
    )


def _ad_hoc_command(*, receipt_id: UUID) -> CreateNotificationCommand:
    return CreateNotificationCommand(
        user_id=TEST_USER_ID,
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="warranty_expiry",
        title="보증 만료 임박",
        message="냉장고 보증이 7일 뒤 만료돼요.",
        resource_type="receipt",
        resource_id=receipt_id,
        metadata={"subCategory": "warranty"},
    )


async def _notification_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(UserNotification)) or 0


async def _outbox_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(OutboxEvent)) or 0


async def _occurrence_count(session: AsyncSession) -> int:
    return (
        await session.scalar(select(func.count()).select_from(NotificationScheduleOccurrence)) or 0
    )


async def _occurrence_key_rows(
    session: AsyncSession,
) -> tuple[tuple[str, str, UUID, date], ...]:
    rows = await session.execute(
        select(
            NotificationScheduleOccurrence.campaign_key,
            NotificationScheduleOccurrence.target_type,
            NotificationScheduleOccurrence.target_id,
            NotificationScheduleOccurrence.occurrence_on,
        ).order_by(NotificationScheduleOccurrence.campaign_key)
    )
    return tuple(rows.tuples())
