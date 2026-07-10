from datetime import timedelta

from app.modules.receipts.application.queries.get_receipt_activity_for_users.port import (
    ReceiptActivityForUsersReader,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivity,
    ReceiptActivityPage,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.port import (
    ReceiptsExpiringOnReader,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.query import (
    ListReceiptsExpiringOnQuery,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceipt,
    ExpiringReceiptsPage,
)
from app.modules.users.application.queries.list_user_registration_facts.query import (
    ListUserRegistrationFactsQuery,
    UserRegistrationFactCursor,
)
from app.modules.users.application.queries.list_user_registration_facts.reader import (
    UserRegistrationFactsReader,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFact,
    UserRegistrationFactsPage,
)


class ExpiringReceiptsReaderFake(ReceiptsExpiringOnReader):
    def __init__(self, receipts: tuple[ExpiringReceipt, ...]) -> None:
        self._receipts = receipts
        self.queries: list[ListReceiptsExpiringOnQuery] = []

    async def list_receipts_expiring_on(
        self,
        *,
        query: ListReceiptsExpiringOnQuery,
    ) -> ExpiringReceiptsPage:
        self.queries.append(query)
        receipts = tuple(
            receipt
            for receipt in self._receipts
            if receipt.expires_on == query.target_date + timedelta(days=query.offset_days)
            and (query.cursor_receipt_id is None or receipt.receipt_id > query.cursor_receipt_id)
        )
        page = receipts[: query.limit]
        has_next = len(receipts) > query.limit
        return ExpiringReceiptsPage(
            receipts=page,
            next_cursor_receipt_id=page[-1].receipt_id if has_next else None,
            has_next=has_next,
            limit=query.limit,
        )


class ReceiptActivityForUsersReaderFake(ReceiptActivityForUsersReader):
    def __init__(self, activities: tuple[ReceiptActivity, ...]) -> None:
        self._activities = activities
        self.queries: list[GetReceiptActivityForUsersQuery] = []

    async def get_receipt_activity_for_users(
        self,
        *,
        query: GetReceiptActivityForUsersQuery,
    ) -> ReceiptActivityPage:
        self.queries.append(query)
        activities = tuple(
            activity
            for activity in self._activities
            if activity.user_id in query.user_ids
            and (query.cursor_user_id is None or activity.user_id > query.cursor_user_id)
            and (
                query.recent_since is None
                or activity.last_receipt_created_at is None
                or activity.last_receipt_created_at < query.recent_since
            )
        )
        page = activities[: query.limit]
        has_next = len(activities) > query.limit
        return ReceiptActivityPage(
            activities=page,
            next_cursor_user_id=page[-1].user_id if has_next else None,
            has_next=has_next,
            limit=query.limit,
        )


class UserRegistrationFactsReaderFake(UserRegistrationFactsReader):
    def __init__(self, facts: tuple[UserRegistrationFact, ...]) -> None:
        self._facts = facts
        self.queries: list[ListUserRegistrationFactsQuery] = []

    async def list_registration_facts(
        self,
        *,
        query: ListUserRegistrationFactsQuery,
    ) -> UserRegistrationFactsPage:
        self.queries.append(query)
        facts = _facts_after_cursor(facts=self._facts, cursor=query.cursor)
        page = facts[: query.batch_size]
        next_cursor = (
            UserRegistrationFactCursor(
                registered_at=page[-1].registered_at,
                user_id=page[-1].user_id,
            )
            if len(facts) > query.batch_size
            else None
        )
        return UserRegistrationFactsPage(facts=page, next_cursor=next_cursor)


def _facts_after_cursor(
    *,
    facts: tuple[UserRegistrationFact, ...],
    cursor: UserRegistrationFactCursor | None,
) -> tuple[UserRegistrationFact, ...]:
    if cursor is None:
        return facts
    return tuple(
        fact
        for fact in facts
        if (fact.registered_at, fact.user_id) > (cursor.registered_at, cursor.user_id)
    )
