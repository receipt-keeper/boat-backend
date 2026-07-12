from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivity,
    ReceiptActivityPage,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.use_case import (
    GetReceiptActivityForUsersQueryUseCase,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceipt,
    ExpiringReceiptsPage,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.use_case import (
    ListReceiptsExpiringOnQueryUseCase,
)

TARGET_DATE = date(2026, 7, 9)
RECENT_SINCE = datetime(2026, 7, 1, 15, 0, tzinfo=UTC)
OBSERVED_BEFORE = datetime(2026, 7, 9, 15, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000101")
RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000201")
type _MalformedQueryFactory = Callable[
    [],
    ListReceiptsExpiringOnQuery | GetReceiptActivityForUsersQuery,
]


@dataclass
class _ExpiringReceiptsReader:
    page: ExpiringReceiptsPage
    received_query: ListReceiptsExpiringOnQuery | None = None

    async def list_receipts_expiring_on(
        self,
        *,
        query: ListReceiptsExpiringOnQuery,
    ) -> ExpiringReceiptsPage:
        self.received_query = query
        return self.page


@dataclass
class _ReceiptActivityReader:
    page: ReceiptActivityPage
    received_query: GetReceiptActivityForUsersQuery | None = None

    async def get_receipt_activity_for_users(
        self,
        *,
        query: GetReceiptActivityForUsersQuery,
    ) -> ReceiptActivityPage:
        self.received_query = query
        return self.page


async def test_list_receipts_expiring_on_delegates_to_narrow_reader() -> None:
    query = ListReceiptsExpiringOnQuery(
        target_date=TARGET_DATE,
        offset_days=30,
        observed_before=OBSERVED_BEFORE,
        limit=10,
    )
    expected_page = ExpiringReceiptsPage(
        receipts=(
            ExpiringReceipt(
                user_id=USER_ID,
                receipt_id=RECEIPT_ID,
                item_name="보증 만료 예정 냉장고",
                sub_category="냉장고",
                expires_on=date(2026, 8, 8),
                created_at=datetime(2026, 7, 8, 15, 0, tzinfo=UTC),
            ),
        ),
        next_cursor_receipt_id=None,
        has_next=False,
        limit=10,
    )
    reader = _ExpiringReceiptsReader(page=expected_page)

    result = await ListReceiptsExpiringOnQueryUseCase(reader=reader).execute(query)

    assert result == expected_page
    assert reader.received_query == query


async def test_get_receipt_activity_for_users_delegates_to_narrow_reader() -> None:
    query = GetReceiptActivityForUsersQuery(
        user_ids=(USER_ID,),
        limit=10,
        recent_since=RECENT_SINCE,
        observed_before=OBSERVED_BEFORE,
    )
    expected_page = ReceiptActivityPage(
        activities=(
            ReceiptActivity(
                user_id=USER_ID,
                last_receipt_created_at=datetime(2026, 7, 1, 23, 59, tzinfo=UTC),
                receipt_count=2,
                cursor_user_id=USER_ID,
            ),
        ),
        next_cursor_user_id=None,
        has_next=False,
        limit=10,
    )
    reader = _ReceiptActivityReader(page=expected_page)

    result = await GetReceiptActivityForUsersQueryUseCase(reader=reader).execute(query)

    assert result == expected_page
    assert reader.received_query == query


@pytest.mark.parametrize(
    ("make_query", "expected_details"),
    [
        (
            lambda: ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=-1,
                observed_before=OBSERVED_BEFORE,
                limit=10,
            ),
            [("offsetDays", "보증 알림 후보 조회 offsetDays가 올바르지 않습니다.")],
        ),
        (
            lambda: ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=30,
                observed_before=OBSERVED_BEFORE,
                limit=0,
            ),
            [("batchSize", "보증 알림 후보 조회 batchSize가 올바르지 않습니다.")],
        ),
        (
            lambda: ListReceiptsExpiringOnQuery(
                target_date=datetime(2026, 7, 9, tzinfo=UTC),
                offset_days=30,
                observed_before=OBSERVED_BEFORE,
                limit=10,
            ),
            [("targetDate", "만료 예정 영수증 조회 targetDate가 올바르지 않습니다.")],
        ),
        (
            lambda: GetReceiptActivityForUsersQuery(
                user_ids=(USER_ID,),
                limit=-1,
                recent_since=None,
                observed_before=OBSERVED_BEFORE,
            ),
            [("batchSize", "영수증 등록 활동 후보 조회 batchSize가 올바르지 않습니다.")],
        ),
        (
            lambda: GetReceiptActivityForUsersQuery(
                user_ids=(USER_ID,),
                limit=10,
                recent_since=datetime(2026, 7, 2, 0, 0),
                observed_before=OBSERVED_BEFORE,
            ),
            [("recentSince", "영수증 등록 활동 후보 조회 recentSince가 올바르지 않습니다.")],
        ),
    ],
)
def test_scheduler_facing_query_contracts_preserve_validation(
    make_query: _MalformedQueryFactory,
    expected_details: list[tuple[str, str]],
) -> None:
    with pytest.raises(ValidationError) as error:
        make_query()

    assert [(detail.field, detail.message) for detail in error.value.details] == expected_details


@pytest.mark.parametrize(
    ("make_query", "expected_details"),
    [
        (
            lambda: ListReceiptsExpiringOnQuery(
                target_date=TARGET_DATE,
                offset_days=30,
                observed_before=datetime(2026, 7, 9, 15, 0),
                limit=10,
            ),
            [("observedBefore", "보증 알림 후보 조회 observedBefore가 올바르지 않습니다.")],
        ),
        (
            lambda: GetReceiptActivityForUsersQuery(
                user_ids=(USER_ID,),
                limit=10,
                recent_since=None,
                observed_before=datetime(2026, 7, 9, 15, 0),
            ),
            [("observedBefore", "영수증 등록 활동 후보 조회 observedBefore가 올바르지 않습니다.")],
        ),
    ],
)
def test_scheduler_fact_queries_reject_naive_observation_cutoff(
    make_query: _MalformedQueryFactory,
    expected_details: list[tuple[str, str]],
) -> None:
    with pytest.raises(ValidationError) as error:
        make_query()

    assert [(detail.field, detail.message) for detail in error.value.details] == expected_details
