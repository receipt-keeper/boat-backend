import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_dispatcher import EventDispatcher
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.serialization import EventTypeRegistry, deserialize_event

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
        threshold = self._clock() - timedelta(seconds=self._redeliver_after_seconds)

        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.occurred_at < threshold,
                OutboxEvent.retry_count < self._max_retry,
            )
            .order_by(OutboxEvent.id)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = (await session.execute(statement)).scalars().all()

        processed = 0
        for row in rows:
            processed += 1
            try:
                event = deserialize_event(self._registry, row.event_type, row.payload)
                await self._dispatcher.dispatch([event])
            except Exception:
                row.retry_count += 1
                logger.warning(
                    "outbox 이벤트 재발행에 실패했습니다. id=%s event_type=%s retry_count=%d",
                    row.id,
                    row.event_type,
                    row.retry_count,
                    exc_info=True,
                )
                continue

            await session.delete(row)

        await session.commit()
        return processed

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
