from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import RowMapping, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.db.session import build_engine

_EXPECTED_MESSAGE_TYPE_CHECK = "ck_user_notifications_message_type_allowed"
_EXPECTED_CATEGORY_CHECK = "ck_user_notifications_category_allowed"
_EXPECTED_RESOURCE_PAIR_CHECK = "ck_user_notifications_resource_pair"

_PUSH_TITLE_BY_KIND = {
    "warranty_notice": "보증 기간 안내",
    "warranty_warning": "보증 만료 주의",
    "warranty_risk": "보증 만료 임박",
    "warranty_expired": "보증 만료",
    "registration_prompt": "영수증 등록 안내",
    "credit_prompt": "크레딧 안내",
    "benefit": "혜택 안내",
}

# (kind, target_type, target_id_is_present)
_LEGACY_ROWS: list[tuple[str, str, bool]] = [
    ("warranty_notice", "receipt", True),
    ("warranty_warning", "receipt", True),
    ("warranty_risk", "receipt", True),
    ("warranty_expired", "receipt", True),
    ("registration_prompt", "receiptUpload", False),
    ("credit_prompt", "none", False),
    ("benefit", "none", False),
    # edge: target_type='receipt' but target_id NULL
    ("warranty_notice", "receipt", False),
]


async def insert_legacy_notification_rows(connection: AsyncConnection) -> dict[str, UUID]:
    """20260704_0012 스키마(구형: target_type/target_id, message_type/title 없음)에
    대표 kind 7종 + 엣지 케이스 1건을 삽입하고, row id를 (kind, target_type, has_id) 키로 반환한다.
    """
    user_id = uuid4()
    row_ids: dict[str, UUID] = {}
    for kind, target_type, has_target_id in _LEGACY_ROWS:
        row_id = uuid4()
        target_id = uuid4() if has_target_id else None
        key = f"{kind}:{target_type}:{'id' if has_target_id else 'noid'}"
        row_ids[key] = row_id
        await connection.execute(
            text(
                """
                INSERT INTO user_notifications
                    (id, user_id, kind, message, target_type, target_id, created_at)
                VALUES
                    (:id, :user_id, :kind, :message, :target_type, :target_id, :created_at)
                """
            ),
            {
                "id": row_id,
                "user_id": user_id,
                "kind": kind,
                "message": f"{kind} message",
                "target_type": target_type,
                "target_id": target_id,
                "created_at": datetime.now(UTC),
            },
        )
    return row_ids


async def assert_backfill_is_correct(database_url: str, row_ids: dict[str, UUID]) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            await _assert_message_type_backfill(connection, row_ids)
            await _assert_category_backfill(connection, row_ids)
            await _assert_title_backfill(connection, row_ids)
            await _assert_resource_pair_backfill(connection, row_ids)
            await _assert_metadata_backfill(connection, row_ids)
            await _assert_not_null_constraints(connection)
            await _assert_check_constraint_names(connection)
        await _assert_resource_pair_check_rejects_partial_pair(engine)
        await _assert_category_check_rejects_unknown_value(engine)
    finally:
        await engine.dispose()


async def _row(connection: AsyncConnection, row_id: UUID) -> RowMapping:
    result = await connection.execute(
        text(
            """
            SELECT message_type, category, title, kind, resource_type, resource_id
            FROM user_notifications
            WHERE id = :id
            """
        ),
        {"id": row_id},
    )
    row = result.mappings().one()
    return row


async def _assert_message_type_backfill(
    connection: AsyncConnection, row_ids: dict[str, UUID]
) -> None:
    for key, row_id in row_ids.items():
        row = await _row(connection, row_id)
        kind = key.split(":", 1)[0]
        expected_message_type = "marketing" if kind == "benefit" else "transactional"
        assert row["message_type"] == expected_message_type, key


async def _assert_category_backfill(connection: AsyncConnection, row_ids: dict[str, UUID]) -> None:
    for key, row_id in row_ids.items():
        row = await _row(connection, row_id)
        kind = key.split(":", 1)[0]
        expected_category = (
            "warranty"
            if kind.startswith("warranty_")
            else "benefit"
            if kind in {"benefit", "credit_prompt", "receipt_analysis_reminder"}
            else "product_management"
        )
        assert row["category"] == expected_category, key


async def _assert_title_backfill(connection: AsyncConnection, row_ids: dict[str, UUID]) -> None:
    for key, row_id in row_ids.items():
        row = await _row(connection, row_id)
        kind = key.split(":", 1)[0]
        expected_title = _PUSH_TITLE_BY_KIND.get(kind, "알림")
        assert row["title"] == expected_title, key


async def _assert_resource_pair_backfill(
    connection: AsyncConnection, row_ids: dict[str, UUID]
) -> None:
    # ('receipt', uuid) rows keep the pair.
    for key, row_id in row_ids.items():
        _kind, target_type, has_id = key.split(":")
        row = await _row(connection, row_id)
        if target_type == "receipt" and has_id == "id":
            assert row["resource_type"] == "receipt", key
            assert row["resource_id"] is not None, key
        else:
            # receiptUpload / none / receipt+NULL edge -> pair cleared to NULL
            assert row["resource_type"] is None, key
            assert row["resource_id"] is None, key


async def _assert_not_null_constraints(connection: AsyncConnection) -> None:
    for column_name in ("category", "message_type", "title", "metadata"):
        is_nullable = await connection.scalar(
            text(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'user_notifications'
                  AND column_name = :column_name
                """
            ),
            {"column_name": column_name},
        )
        assert is_nullable == "NO", column_name


async def _assert_metadata_backfill(connection: AsyncConnection, row_ids: dict[str, UUID]) -> None:
    for key, row_id in row_ids.items():
        result = await connection.execute(
            text("SELECT metadata FROM user_notifications WHERE id = :id"),
            {"id": row_id},
        )
        metadata = result.scalar_one()
        assert metadata == {}, key


async def _assert_check_constraint_names(connection: AsyncConnection) -> None:
    constraint_rows = await connection.execute(
        text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = to_regclass('public.user_notifications')
              AND contype = 'c'
            """
        )
    )
    constraint_names = {row[0] for row in constraint_rows.tuples()}
    assert _EXPECTED_MESSAGE_TYPE_CHECK in constraint_names
    assert _EXPECTED_CATEGORY_CHECK in constraint_names
    assert _EXPECTED_RESOURCE_PAIR_CHECK in constraint_names


async def _assert_resource_pair_check_rejects_partial_pair(engine: AsyncEngine) -> None:
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_notifications
                        (id, user_id, kind, message_type, title, message,
                         resource_type, created_at)
                    VALUES
                        (:id, :user_id, 'benefit', 'marketing', '알림', 'msg',
                         'receipt', :created_at)
                    """
                ),
                {"id": uuid4(), "user_id": uuid4(), "created_at": datetime.now(UTC)},
            )


async def _assert_category_check_rejects_unknown_value(engine: AsyncEngine) -> None:
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO user_notifications "
                    "(id, user_id, category, kind, message_type, title, message, created_at) "
                    "VALUES (:id, :user_id, '알 수 없음', 'benefit', 'marketing', '알림', "
                    "'msg', :created_at)"
                ),
                {"id": uuid4(), "user_id": uuid4(), "created_at": datetime.now(UTC)},
            )
