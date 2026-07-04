"""갱신이 끊긴 FCM 푸시 토큰을 정리하는 배치 잡.

실행: uv run python -m app.modules.notifications.jobs.cleanup_stale_tokens
스케줄링은 배포 환경의 크론(예: K8s CronJob)이 담당한다.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config.settings import get_settings
from app.core.db.session import build_engine, build_session_factory
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.notifications.application.commands.delete_stale_push_tokens.command import (
    DeleteStalePushTokensCommand,
)
from app.modules.notifications.application.commands.delete_stale_push_tokens.use_case import (
    DeleteStalePushTokensCommandUseCase,
)
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyPushTokenRepository,
)

logger = logging.getLogger(__name__)


async def run() -> int:
    settings = get_settings()
    older_than = datetime.now(UTC) - timedelta(days=settings.push_token_stale_days)

    engine = build_engine(settings.database_url)
    try:
        sessions = build_session_factory(engine)
        async with sessions() as session:
            use_case = DeleteStalePushTokensCommandUseCase(
                push_token_repository=SqlAlchemyPushTokenRepository(session),
                unit_of_work=SqlAlchemyUnitOfWork(session),
            )
            result = await use_case.execute(DeleteStalePushTokensCommand(older_than=older_than))
    finally:
        await engine.dispose()

    logger.info(
        "%s 이전에 갱신이 멈춘 푸시 토큰 %d건을 삭제했습니다.",
        older_than.isoformat(),
        result.deleted_count,
    )
    return result.deleted_count


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
