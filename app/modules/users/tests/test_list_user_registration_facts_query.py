import dataclasses
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.domain.exceptions import ValidationError
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
from app.modules.users.application.queries.list_user_registration_facts.use_case import (
    ListUserRegistrationFactsQueryUseCase,
)


class InMemoryUserRegistrationFactsReader(UserRegistrationFactsReader):
    def __init__(self, page: UserRegistrationFactsPage) -> None:
        self.page = page
        self.received_query: ListUserRegistrationFactsQuery | None = None

    async def list_registration_facts(
        self,
        *,
        query: ListUserRegistrationFactsQuery,
    ) -> UserRegistrationFactsPage:
        self.received_query = query
        return self.page


async def test_list_user_registration_facts_returns_reader_page_without_scheduler_policy() -> None:
    cursor = UserRegistrationFactCursor(
        registered_at=datetime(2026, 7, 2, 9, tzinfo=UTC),
        user_id=UUID(int=2),
    )
    page = UserRegistrationFactsPage(
        facts=(
            UserRegistrationFact(
                user_id=UUID(int=1),
                registered_at=datetime(2026, 7, 2, 9, tzinfo=UTC),
            ),
        ),
        next_cursor=cursor,
    )
    reader = InMemoryUserRegistrationFactsReader(page)
    query = ListUserRegistrationFactsQuery(batch_size=2)

    result = await ListUserRegistrationFactsQueryUseCase(reader=reader).execute(query)

    assert result == page
    assert reader.received_query is query
    assert {field.name for field in dataclasses.fields(page.facts[0])} == {
        "user_id",
        "registered_at",
    }


def test_list_user_registration_facts_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ListUserRegistrationFactsQuery(batch_size=0)

    assert tuple((detail.field, detail.message) for detail in exc_info.value.details) == (
        ("batchSize", "사용자 등록 사실 조회 batchSize가 올바르지 않습니다."),
    )


def test_list_user_registration_facts_rejects_naive_window_boundary() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ListUserRegistrationFactsQuery(
            batch_size=1,
            registered_after=datetime(2026, 7, 1, 9),
        )

    assert tuple((detail.field, detail.message) for detail in exc_info.value.details) == (
        ("registeredAfter", "사용자 등록 시각 범위가 올바르지 않습니다."),
    )


def test_list_user_registration_facts_rejects_invalid_window_order() -> None:
    boundary = datetime(2026, 7, 2, 9, tzinfo=UTC)
    with pytest.raises(ValidationError) as exc_info:
        ListUserRegistrationFactsQuery(
            batch_size=1,
            registered_after=boundary,
            registered_before=boundary,
        )

    assert tuple((detail.field, detail.message) for detail in exc_info.value.details) == (
        ("registeredAt", "사용자 등록 시각 범위가 올바르지 않습니다."),
    )


def test_user_registration_fact_cursor_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError) as exc_info:
        UserRegistrationFactCursor(
            registered_at=datetime(2026, 7, 2, 9),
            user_id=UUID(int=1),
        )

    assert tuple((detail.field, detail.message) for detail in exc_info.value.details) == (
        ("cursor", "사용자 등록 사실 조회 cursor가 올바르지 않습니다."),
    )
