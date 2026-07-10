from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceipt,
)
from app.modules.receipts.dependencies import (
    build_get_receipt_activity_for_users_query_use_case,
    build_list_receipts_expiring_on_query_use_case,
)
from app.modules.receipts.infrastructure.persistence import orm

TARGET_DATE = date(2026, 7, 9)
TARGET_START = datetime.combine(TARGET_DATE, time.min, tzinfo=UTC)
KST_RECENT_SINCE = datetime(2026, 7, 1, 15, 0, tzinfo=UTC)

D30_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000030")
SECOND_D30_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000031")
D14_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000014")
D10_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000010")
D7_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000007")
D0_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000001")
D31_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000032")
D1_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000002")
EXPIRED_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000099")
INACTIVE_LATEST_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000201")
INACTIVE_OLDER_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000202")
RECENT_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000203")
BOUNDARY_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000204")

ZERO_RECEIPT_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
INACTIVE_USER_ID = UUID("00000000-0000-0000-0000-000000000102")
RECENT_USER_ID = UUID("00000000-0000-0000-0000-000000000103")
BOUNDARY_USER_ID = UUID("00000000-0000-0000-0000-000000000104")


@dataclass(frozen=True, slots=True)
class _SeedReceipt:
    receipt_id: UUID
    user_id: UUID
    item_name: str
    expires_on: date
    created_at: datetime


async def test_list_receipts_expiring_on_matches_exact_offsets_and_pages(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    zero_user = ZERO_RECEIPT_USER_ID
    inactive_user = INACTIVE_USER_ID
    recent_user = RECENT_USER_ID
    second_d30 = SECOND_D30_RECEIPT_ID

    async with postgres_session_factory() as session:
        use_case = build_list_receipts_expiring_on_query_use_case(session)
        session.add_all(
            _receipt_records(
                (
                    _SeedReceipt(D30_RECEIPT_ID, zero_user, "D-30 냉장고", _e(30), _c(20)),
                    _SeedReceipt(second_d30, inactive_user, "D-30 세탁기", _e(30), _c(19)),
                    _SeedReceipt(D14_RECEIPT_ID, inactive_user, "D-14 청소기", _e(14), _c(18)),
                    _SeedReceipt(D10_RECEIPT_ID, inactive_user, "D-10 비PM 후보", _e(10), _c(18)),
                    _SeedReceipt(D7_RECEIPT_ID, recent_user, "D-7 공기청정기", _e(7), _c(17)),
                    _SeedReceipt(D0_RECEIPT_ID, recent_user, "D-Day 노트북", _e(0), _c(16)),
                    _SeedReceipt(D31_RECEIPT_ID, zero_user, "D-31 제외", _e(31), _c(15)),
                    _SeedReceipt(D1_RECEIPT_ID, zero_user, "D-1 제외", _e(1), _c(14)),
                    _SeedReceipt(EXPIRED_RECEIPT_ID, zero_user, "만료 제외", _e(-1), _c(13)),
                )
            )
        )
        await session.flush()

        first_d30_page = await use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=30,
                limit=1,
            )
        )
        second_d30_page = await use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=30,
                limit=1,
                cursor_receipt_id=first_d30_page.next_cursor_receipt_id,
            )
        )
        d14_page = await use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=14,
                limit=10,
            )
        )
        d7_page = await use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=7,
                limit=10,
            )
        )
        d10_page = await use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=10,
                limit=10,
            )
        )
        d0_page = await use_case.execute(
            ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=0,
                limit=10,
            )
        )

    assert [candidate.receipt_id for candidate in first_d30_page.receipts] == [D30_RECEIPT_ID]
    assert first_d30_page.receipts[0].item_name == "D-30 냉장고"
    assert first_d30_page.receipts[0].expires_on == TARGET_DATE + timedelta(days=30)
    assert first_d30_page.receipts[0].days_until_expiry == 30
    assert first_d30_page.next_cursor_receipt_id == D30_RECEIPT_ID
    assert first_d30_page.has_next is True

    assert [candidate.receipt_id for candidate in second_d30_page.receipts] == [
        SECOND_D30_RECEIPT_ID
    ]
    assert second_d30_page.next_cursor_receipt_id is None
    assert second_d30_page.has_next is False

    assert _candidate_ids(d14_page.receipts) == (D14_RECEIPT_ID,)
    assert _candidate_ids(d10_page.receipts) == (D10_RECEIPT_ID,)
    assert d10_page.receipts[0].days_until_expiry == 10
    assert _candidate_ids(d7_page.receipts) == (D7_RECEIPT_ID,)
    assert _candidate_ids(d0_page.receipts) == (D0_RECEIPT_ID,)


async def test_get_receipt_activity_for_users_uses_scheduler_provided_recent_since(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    inactive_last_receipt_at = TARGET_START - timedelta(days=8)
    inactive_older_receipt_at = TARGET_START - timedelta(days=30)
    recent_receipt_at = TARGET_START - timedelta(days=6)
    boundary_receipt_at = KST_RECENT_SINCE
    inactive_user = INACTIVE_USER_ID
    recent_user = RECENT_USER_ID
    boundary_user = BOUNDARY_USER_ID

    async with postgres_session_factory() as session:
        use_case = build_get_receipt_activity_for_users_query_use_case(session)
        session.add_all(
            _receipt_records(
                (
                    _SeedReceipt(
                        INACTIVE_LATEST_RECEIPT_ID,
                        inactive_user,
                        "비활성 최신 영수증",
                        _e(100),
                        inactive_last_receipt_at,
                    ),
                    _SeedReceipt(
                        INACTIVE_OLDER_RECEIPT_ID,
                        inactive_user,
                        "비활성 과거 영수증",
                        _e(100),
                        inactive_older_receipt_at,
                    ),
                    _SeedReceipt(
                        RECENT_RECEIPT_ID,
                        recent_user,
                        "최근 영수증",
                        _e(100),
                        recent_receipt_at,
                    ),
                    _SeedReceipt(
                        BOUNDARY_RECEIPT_ID,
                        boundary_user,
                        "7일 경계 영수증",
                        _e(100),
                        boundary_receipt_at,
                    ),
                )
            )
        )
        await session.flush()

        first_page = await use_case.execute(
            GetReceiptActivityForUsersQuery(
                user_ids=(
                    ZERO_RECEIPT_USER_ID,
                    INACTIVE_USER_ID,
                    RECENT_USER_ID,
                    BOUNDARY_USER_ID,
                ),
                limit=1,
                recent_since=KST_RECENT_SINCE,
            )
        )
        second_page = await use_case.execute(
            GetReceiptActivityForUsersQuery(
                user_ids=(
                    ZERO_RECEIPT_USER_ID,
                    INACTIVE_USER_ID,
                    RECENT_USER_ID,
                    BOUNDARY_USER_ID,
                ),
                limit=10,
                recent_since=KST_RECENT_SINCE,
                cursor_user_id=first_page.next_cursor_user_id,
            )
        )

    assert [candidate.user_id for candidate in first_page.activities] == [ZERO_RECEIPT_USER_ID]
    assert first_page.activities[0].last_receipt_created_at is None
    assert first_page.activities[0].receipt_count == 0
    assert first_page.activities[0].cursor_user_id == ZERO_RECEIPT_USER_ID
    assert first_page.next_cursor_user_id == ZERO_RECEIPT_USER_ID
    assert first_page.has_next is True

    assert [candidate.user_id for candidate in second_page.activities] == [INACTIVE_USER_ID]
    assert second_page.activities[0].last_receipt_created_at == inactive_last_receipt_at
    assert second_page.activities[0].receipt_count == 2
    assert second_page.activities[0].cursor_user_id == INACTIVE_USER_ID
    assert second_page.next_cursor_user_id is None
    assert second_page.has_next is False


async def test_get_receipt_activity_for_users_returns_all_counts_without_recent_since(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 영수증이 없는 사용자와 최근 영수증을 등록한 사용자가 있다.
    async with postgres_session_factory() as session:
        use_case = build_get_receipt_activity_for_users_query_use_case(session)
        session.add(
            _receipt_record(
                _SeedReceipt(
                    RECENT_RECEIPT_ID,
                    RECENT_USER_ID,
                    "최근 영수증",
                    _e(100),
                    TARGET_START,
                )
            )
        )
        await session.flush()

        page = await use_case.execute(
            GetReceiptActivityForUsersQuery(
                user_ids=(ZERO_RECEIPT_USER_ID, RECENT_USER_ID),
                limit=10,
                recent_since=None,
            )
        )

    # When/Then: scheduler가 recent filter를 요청하지 않으면 모든 count fact를 받는다.
    assert [(activity.user_id, activity.receipt_count) for activity in page.activities] == [
        (ZERO_RECEIPT_USER_ID, 0),
        (RECENT_USER_ID, 1),
    ]


def _receipt_record(seed: _SeedReceipt) -> orm.Receipt:
    return orm.Receipt(
        id=seed.receipt_id,
        user_id=seed.user_id,
        item_name=seed.item_name,
        payment_date=seed.expires_on - timedelta(days=365),
        period_months=12,
        expires_on=seed.expires_on,
        requires_physical_receipt=False,
        created_at=seed.created_at,
        updated_at=seed.created_at,
    )


def _receipt_records(seeds: tuple[_SeedReceipt, ...]) -> tuple[orm.Receipt, ...]:
    return tuple(_receipt_record(seed) for seed in seeds)


def _e(days: int) -> date:
    return TARGET_DATE + timedelta(days=days)


def _c(days: int) -> datetime:
    return TARGET_START - timedelta(days=days)


def _candidate_ids(candidates: tuple[ExpiringReceipt, ...]) -> tuple[UUID, ...]:
    return tuple(candidate.receipt_id for candidate in candidates)
