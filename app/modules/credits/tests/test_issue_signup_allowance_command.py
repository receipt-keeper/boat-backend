from datetime import UTC, datetime, timedelta
from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.application.commands.grant_credit.use_case import (
    GrantCreditCommandUseCase,
)
from app.modules.credits.application.commands.issue_signup_allowance.command import (
    IssueSignupAllowanceCommand,
)
from app.modules.credits.application.commands.issue_signup_allowance.result import (
    SignupAllowanceOutcome,
)
from app.modules.credits.application.commands.issue_signup_allowance.use_case import (
    IssueSignupAllowanceCommandUseCase,
)
from app.modules.credits.dependencies import build_credits_event_registry
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000701")
CURRENT_HANDLE = "v2:" + "a" * 64
RETIRED_HANDLE = "v1:" + "a" * 64


def _build_use_case(session: AsyncSession) -> IssueSignupAllowanceCommandUseCase:
    credit_repository = SqlAlchemyCreditRepository(session)
    unit_of_work = SqlAlchemyUnitOfWork(session)
    grant_credit_command_use_case = GrantCreditCommandUseCase(
        credit_repository=credit_repository,
        unit_of_work=unit_of_work,
        event_publisher=OutboxEventPublisher(
            session=session,
            registry=build_credits_event_registry(),
        ),
    )
    return IssueSignupAllowanceCommandUseCase(
        credit_repository=credit_repository,
        grant_credit_command_use_case=grant_credit_command_use_case,
        unit_of_work=unit_of_work,
    )


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=180)


async def test_first_issue_grants_five_credits_with_signup_allowance_idempotency_key(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        result = await _build_use_case(session).execute(
            IssueSignupAllowanceCommand(
                user_id=USER_ID,
                subject_handle=CURRENT_HANDLE,
                candidate_handles=(CURRENT_HANDLE,),
            )
        )

    assert result.outcome == SignupAllowanceOutcome.ISSUED
    assert result.total_granted_count == 5
    assert result.remaining_count == 5

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert len(saved_transactions) == 1
    assert saved_transactions[0].idempotency_key == f"signup-allowance:{CURRENT_HANDLE}"
    assert saved_transactions[0].purge_after is None
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "CreditGranted"


async def test_repeat_call_with_same_handle_does_not_regrant_and_reactivates_claim(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    command = IssueSignupAllowanceCommand(
        user_id=USER_ID,
        subject_handle=CURRENT_HANDLE,
        candidate_handles=(CURRENT_HANDLE,),
    )
    async with postgres_session_factory() as session:
        await _build_use_case(session).execute(command)

    # 탈퇴 후 보존 기간 내 재가입을 흉내내기 위해 claim에 purge_after를 심어 둔다.
    async with postgres_session_factory() as session:
        transaction = await session.scalar(
            select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
        )
        assert transaction is not None
        transaction.purge_after = _future()
        await session.commit()

    async with postgres_session_factory() as session:
        result = await _build_use_case(session).execute(command)

    assert result.outcome == SignupAllowanceOutcome.REACTIVATED

    async with postgres_session_factory() as session:
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    # 재지급 없음: 원장 row는 최초 1건 그대로, purge_after만 NULL로 되돌아간다.
    assert len(saved_transactions) == 1
    assert saved_transactions[0].purge_after is None
    # 재활성화 분기는 신규 CreditGranted 이벤트를 발행하지 않는다(최초 1건만 존재).
    assert len(saved_outbox_events) == 1


async def test_cross_version_candidate_handle_hit_reactivates_without_regrant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # 은퇴한 v1 handle로 최초 지급된 claim이 있는 상태를 만든다.
    async with postgres_session_factory() as session:
        await _build_use_case(session).execute(
            IssueSignupAllowanceCommand(
                user_id=USER_ID,
                subject_handle=RETIRED_HANDLE,
                candidate_handles=(RETIRED_HANDLE,),
            )
        )
        transaction = await session.scalar(
            select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
        )
        assert transaction is not None
        transaction.purge_after = _future()
        await session.commit()

    # 키 회전 후 현행 handle은 v2이지만, 조회 후보 목록에 은퇴한 v1도 포함된다.
    async with postgres_session_factory() as session:
        result = await _build_use_case(session).execute(
            IssueSignupAllowanceCommand(
                user_id=USER_ID,
                subject_handle=CURRENT_HANDLE,
                candidate_handles=(CURRENT_HANDLE, RETIRED_HANDLE),
            )
        )

    assert result.outcome == SignupAllowanceOutcome.REACTIVATED

    async with postgres_session_factory() as session:
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )

    # 이중 지급 없음: 여전히 v1 handle로 기록된 원장 row 1건뿐이다.
    assert len(saved_transactions) == 1
    assert saved_transactions[0].idempotency_key == f"signup-allowance:{RETIRED_HANDLE}"
    assert saved_transactions[0].purge_after is None


async def test_concurrent_first_issue_grants_exactly_once(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    command = IssueSignupAllowanceCommand(
        user_id=USER_ID,
        subject_handle=CURRENT_HANDLE,
        candidate_handles=(CURRENT_HANDLE,),
    )
    start = anyio.Event()

    async def issue_once() -> None:
        await start.wait()
        async with postgres_session_factory() as session:
            await _build_use_case(session).execute(command)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(issue_once)
        task_group.start_soon(issue_once)
        start.set()

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.remaining_count == 5
    assert len(saved_transactions) == 1
    assert saved_transactions[0].idempotency_key == f"signup-allowance:{CURRENT_HANDLE}"
