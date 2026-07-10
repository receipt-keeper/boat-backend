import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

import anyio

from app.core.config.settings import get_settings
from app.core.db.session import build_engine, build_session_factory
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.notifications.application.commands.create_due_notifications.command import (
    CreateDueNotificationsCommand,
)
from app.modules.notifications.application.commands.create_due_notifications.result import (
    CreateDueNotificationsResult,
)
from app.modules.notifications.dependencies import (
    build_create_due_notifications_command_use_case,
)

logger = logging.getLogger(__name__)


async def run(command: CreateDueNotificationsCommand) -> CreateDueNotificationsResult:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        sessions = build_session_factory(engine)
        async with sessions() as session:
            unit_of_work = SqlAlchemyUnitOfWork(session)
            use_case = build_create_due_notifications_command_use_case(
                session,
                unit_of_work,
            )
            return await use_case.execute(command)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    command = _parse_command(argv)
    result = anyio.run(run, command)
    logger.info(
        "예약 푸시 알림 후보 %d건 중 %d건 생성, %d건 스킵, %d건 실패",
        result.candidates,
        result.created,
        result.skipped,
        result.failed,
    )
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True))


def _parse_command(argv: Sequence[str] | None) -> CreateDueNotificationsCommand:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.notifications.jobs.schedule_push_notifications"
    )
    parser.add_argument("--target-date", type=_parse_date, default=None)
    parser.add_argument("--now", type=_parse_datetime, default=datetime.now(UTC))
    parser.add_argument("--campaign-key", default=None)
    parser.add_argument(
        "--dry-run",
        nargs="?",
        const="true",
        default="false",
        type=_parse_bool,
    )
    parser.add_argument("--batch-size", type=_parse_batch_size, default=100)
    args = parser.parse_args(argv)
    try:
        return CreateDueNotificationsCommand(
            target_date=args.target_date,
            now=args.now,
            campaign_key=args.campaign_key,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    except ValidationError as exc:
        parser.error("; ".join(detail.message for detail in exc.details))


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--target-date는 YYYY-MM-DD 형식이어야 합니다.") from exc


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--now는 ISO-8601 datetime 형식이어야 합니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--now는 timezone offset을 포함해야 합니다.")
    return parsed


def _parse_batch_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--batch-size는 1 이상의 정수여야 합니다.") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("--batch-size는 1 이상의 정수여야 합니다.")
    return parsed


def _parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise argparse.ArgumentTypeError("--dry-run은 true 또는 false여야 합니다.")


def _summary(
    result: CreateDueNotificationsResult,
) -> dict[
    str,
    bool | int | list[dict[str, int | str]],
]:
    return {
        "dryRun": result.dry_run,
        "candidates": result.candidates,
        "created": result.created,
        "skipped": result.skipped,
        "failed": result.failed,
        "rules": [
            {
                "campaignKey": rule.campaign_key,
                "candidates": rule.candidates,
                "created": rule.created,
                "skipped": rule.skipped,
                "failed": rule.failed,
            }
            for rule in result.rules
        ],
    }


if __name__ == "__main__":
    main()
