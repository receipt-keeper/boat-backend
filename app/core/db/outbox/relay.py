import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_dispatcher import EventDispatcher
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.serialization import EventTypeRegistry, deserialize_event

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _ClaimedEvent:
    event_id: UUID
    event_type: str
    payload: dict[str, object]
    retry_count: int
    claimed_at: datetime


class OutboxRelay:
    """미발행 outbox row를 선별해 재발행하는 폴러.

    즉시 발행 경로(delete-then-dispatch)와 별개의 안전망이다. `occurred_at`이
    `redeliver_after_seconds`보다 오래되고 `retry_count`가 `max_retry` 미만인
    row만 대상으로 삼아, 즉시 발행 경로와의 경합 창을 피한다.
    """

    def __init__(
        self,
        *,
        registry: EventTypeRegistry,
        dispatcher: EventDispatcher,
        redeliver_after_seconds: int,
        max_retry: int,
        batch_size: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._registry = registry
        self._dispatcher = dispatcher
        self._redeliver_after_seconds = redeliver_after_seconds
        self._max_retry = max_retry
        self._batch_size = batch_size
        self._clock = clock

    async def run_once(self, session: AsyncSession) -> int:
        """대상 배치를 한 번 처리하고 처리 건수를 반환한다."""
        processed = 0
        for _ in range(self._batch_size):
            claim = await self._claim_next(session)
            if claim is None:
                break

            processed += 1
            try:
                event = deserialize_event(self._registry, claim.event_type, claim.payload)
                await self._dispatcher.dispatch([event])
            except Exception:
                await self._mark_failed(session, claim)
                logger.warning(
                    "outbox 이벤트 재발행에 실패했습니다. id=%s event_type=%s retry_count=%d",
                    claim.event_id,
                    claim.event_type,
                    claim.retry_count + 1,
                    exc_info=True,
                )
                continue

            await self._delete_succeeded(session, claim)

        return processed

    async def _claim_next(self, session: AsyncSession) -> _ClaimedEvent | None:
        claimed_at = self._clock()
        threshold = claimed_at - timedelta(seconds=self._redeliver_after_seconds)
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.occurred_at < threshold,
                OutboxEvent.retry_count < self._max_retry,
            )
            .order_by(OutboxEvent.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            await session.commit()
            return None

        claimed_at = max(
            claimed_at,
            row.occurred_at + timedelta(microseconds=1),
        )
        row.occurred_at = claimed_at
        claim = _ClaimedEvent(
            event_id=row.event_id,
            event_type=row.event_type,
            payload=row.payload,
            retry_count=row.retry_count,
            claimed_at=claimed_at,
        )

        # 한 건을 dispatch 직전에 claim하고 커밋해 행 잠금과 DB 커넥션을 해제한다.
        # 프로세스가 중단되면 retry_count를 소진하지 않고 lease 만료 후 재선택된다.
        await session.commit()
        return claim

    @staticmethod
    async def _delete_succeeded(session: AsyncSession, claim: _ClaimedEvent) -> None:
        await session.execute(
            delete(OutboxEvent).where(
                OutboxEvent.event_id == claim.event_id,
                OutboxEvent.retry_count == claim.retry_count,
                OutboxEvent.occurred_at == claim.claimed_at,
            )
        )
        await session.commit()

    @staticmethod
    async def _mark_failed(session: AsyncSession, claim: _ClaimedEvent) -> None:
        await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.event_id == claim.event_id,
                OutboxEvent.retry_count == claim.retry_count,
                OutboxEvent.occurred_at == claim.claimed_at,
            )
            .values(retry_count=claim.retry_count + 1)
        )
        await session.commit()

    async def run_forever(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        interval_seconds: float,
    ) -> None:
        """`interval_seconds` 주기로 `run_once`를 반복한다.

        `asyncio.CancelledError`를 받으면 진행 중인 배치를 마친 뒤 조용히
        종료한다. 루프 내부에서 발생하는 그 외 예외는 로그만 남기고 폴러를
        계속 실행한다(폴러가 죽으면 안 된다).
        """
        try:
            while True:
                try:
                    async with session_factory() as session:
                        await self.run_once(session)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("outbox 폴러 실행 중 예외가 발생했습니다.", exc_info=True)

                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return
