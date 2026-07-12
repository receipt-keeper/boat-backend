from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.dependencies import (
    build_get_receipt_activity_for_users_query_use_case,
    build_list_receipts_expiring_on_query_use_case,
)
from app.modules.receipts.infrastructure.persistence import orm

TARGET_DATE = date(2026, 7, 9)
OBSERVED_BEFORE = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
WARRANTY_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000030")
INACTIVE_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
ZERO_RECEIPT_USER_ID = UUID("00000000-0000-0000-0000-000000000102")


async def test_receipt_query_contract_characterization(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    inactive_at = datetime(2026, 7, 1, 23, 59, tzinfo=UTC)

    async with postgres_session_factory() as session:
        session.add(
            _receipt(
                receipt_id=WARRANTY_RECEIPT_ID,
                user_id=INACTIVE_USER_ID,
                item_name="보증 만료 예정 냉장고",
                expires_on=TARGET_DATE + timedelta(days=30),
                created_at=inactive_at,
            )
        )
        await session.flush()
        expiring_use_case = build_list_receipts_expiring_on_query_use_case(session)
        activity_use_case = build_get_receipt_activity_for_users_query_use_case(session)

        expiring_page = await expiring_use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=30,
                observed_before=OBSERVED_BEFORE,
                limit=1,
            )
        )
        activity_page = await activity_use_case.execute(
            GetReceiptActivityForUsersQuery(
                user_ids=(ZERO_RECEIPT_USER_ID, INACTIVE_USER_ID),
                limit=10,
                recent_since=datetime(2026, 7, 2, tzinfo=UTC),
                observed_before=OBSERVED_BEFORE,
            )
        )

    assert [(item.receipt_id, item.sub_category) for item in expiring_page.receipts] == [
        (WARRANTY_RECEIPT_ID, None)
    ]
    assert expiring_page.next_cursor_receipt_id is None
    assert expiring_page.has_next is False
    assert [(item.user_id, item.receipt_count) for item in activity_page.activities] == [
        (INACTIVE_USER_ID, 1),
        (ZERO_RECEIPT_USER_ID, 0),
    ]
    assert activity_page.activities[0].last_receipt_created_at == inactive_at
    assert activity_page.next_cursor_user_id is None
    assert activity_page.has_next is False


def _receipt(
    *,
    receipt_id: UUID,
    user_id: UUID,
    item_name: str,
    expires_on: date,
    created_at: datetime,
) -> orm.Receipt:
    return orm.Receipt(
        id=receipt_id,
        user_id=user_id,
        item_name=item_name,
        payment_date=expires_on - timedelta(days=365),
        period_months=12,
        expires_on=expires_on,
        requires_physical_receipt=False,
        created_at=created_at,
        updated_at=created_at,
    )
