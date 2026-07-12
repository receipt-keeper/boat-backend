import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.credits.infrastructure.persistence import orm

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CreditClaimPurger:
    """보존 기간이 지난 가입 보너스 claim(credit_transactions row)을 파기하는 독립 폴러.

    같은 인터벌 폴링 구조(run_once/run_forever, CancelledError 시 조용히 종료, 그 외
    예외는 로그 후 계속)를 다른 백그라운드 재발행 폴러와 동일하게 따르지만, 이 폴러는
    credit_transactions.purge_after만 다루는 별개의 구현이다.
    """

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    async def run_once(self, session: AsyncSession) -> int:
        """purge_after가 경과한 claim row를 한 번 파기하고 삭제 건수를 반환한다."""
        statement = delete(orm.CreditTransaction).where(
            orm.CreditTransaction.purge_after <= self._clock()
        )
        result = cast("CursorResult[Any]", await session.execute(statement))
        await session.commit()
        return result.rowcount or 0

    async def run_forever(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        interval_seconds: float,
    ) -> None:
        """`interval_seconds` 주기로 `run_once`를 반복한다.

        `asyncio.CancelledError`를 받으면 진행 중인 배치를 마친 뒤 조용히 종료한다.
        루프 내부에서 발생하는 그 외 예외는 로그만 남기고 폴러를 계속 실행한다(폴러가
        죽으면 안 된다).
        """
        try:
            while True:
                try:
                    async with session_factory() as session:
                        await self.run_once(session)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("크레딧 claim 파기 중 예외가 발생했습니다.", exc_info=True)

                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            return
