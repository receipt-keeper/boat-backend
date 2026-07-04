from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from fastapi import FastAPI, Request

from app.core.config.settings import Settings
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionAppend,
    CreditTransactionCursor,
    CreditTransactionListItem,
    CreditTransactionListResult,
    CreditTransactionSourceKey,
)
from app.modules.credits.dependencies import get_credit_repository
from app.modules.credits.domain import (
    CreditAction,
    CreditAmount,
    CreditBalance,
    CreditReason,
    UserCredit,
)
from app.modules.users.application.queries.current_user_profile.query import (
    CurrentUserProfileQuery,
)
from app.modules.users.application.queries.current_user_profile.result import (
    CurrentUserProfileResult,
)
from app.modules.users.dependencies import get_current_user_profile_query_use_case

TEST_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000101")
TEST_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000102")
TEST_SESSION_ID: Final = UUID("00000000-0000-0000-0000-000000000103")
EMPTY_CREDITS_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000201")
SEEDED_CREDITS_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000301")
TEST_SETTINGS: Final = Settings(app_name="Boat Backend")
EXPECTED_PUBLIC_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/credits",
        "/api/v1/credits/transactions",
        "/api/v1/receipts",
        "/api/v1/receipts/{receipt_id}",
        "/api/v1/ocr",
        "/api/v1/usage",
        "/api/v1/promotions",
        "/api/v1/promotions/{promotion_id}/redemptions",
        "/api/v1/promotions/redemptions",
        "/api/v1/notifications",
        "/api/v1/notifications/{notification_id}",
        "/api/v1/notifications/settings",
    }
)
FORBIDDEN_PUBLIC_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/receipts/recent",
        "/api/v1/receipts/warranty-expirations",
        "/api/v1/receipt-analysis-allowance",
        "/api/v1/app-config",
        "/api/v1/ocr/receipt",
        "/api/v1/billing-orders",
        "/api/v1/document-analyses",
        "/api/v1/notifications/device-token",
        "/api/v1/notification-reads/{notification_id}",
        "/api/v1/notification-settings",
        "/api/v1/warranty-certificates",
        "/api/v1/warranties",
        "/api/v1/warranties/{warranty_id}",
        "/api/v1/registered-products",
        "/api/v1/products",
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/notifications/devices/{device_id}",
        "/api/v1/credits/free-recharge",
        "/api/v1/credits/free-recharges",
        "/api/v1/credits/grant",
        "/api/v1/credits/grants",
        "/api/v1/credits/recharge",
        "/api/v1/credits/recharges",
        "/api/v1/promotion-codes",
        "/api/v1/promotion-codes/{promotion_code_id}",
    }
)
FORBIDDEN_OPENAPI_PUBLIC_TERMS: Final[frozenset[str]] = frozenset(
    {
        "mock",
        "계약 확인",
        "분석권",
        "원장",
        "트랜잭션",
        "현재 사용자의",
        "billing",
        "receipt-analysis",
        "document-analyses",
        "보증 목록",
        "accountId",
    }
)
FORBIDDEN_ME_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "notificationSettings",
        "notificationEnabled",
        "marketingConsent",
        "pushEnabled",
        "warrantyReminderEnabled",
        "pushToken",
        "pushTokenCount",
        "deviceToken",
        "credits",
        "usage",
        "allowance",
    }
)


class CurrentUserProfileQueryUseCaseStub:
    async def execute(self, query: CurrentUserProfileQuery) -> CurrentUserProfileResult:
        return CurrentUserProfileResult(
            user_id=query.user_id,
            email="contract@example.com",
            name="계약 사용자",
            nickname="계약",
            profile_image_url=None,
        )


class CreditRepositoryStub(CreditRepository):
    async def get_balance(self, *, user_id: UUID) -> CreditBalance:
        if user_id == SEEDED_CREDITS_USER_ID:
            return CreditBalance(
                total_granted_count=15,
                used_count=5,
                remaining_count=10,
            )
        return CreditBalance(
            total_granted_count=0,
            used_count=0,
            remaining_count=0,
        )

    async def get_user_credit_for_update(self, *, user_id: UUID) -> UserCredit:
        raise AssertionError("contract read app should not lock credit balance")

    async def save(self, *, user_credit: UserCredit) -> None:
        raise AssertionError("contract read app should not save credit balance")

    async def append_transaction(
        self,
        *,
        transaction: CreditTransactionAppend,
    ) -> None:
        raise AssertionError("contract read app should not append credit transactions")

    async def flush_pending_writes(self) -> None:
        raise AssertionError("contract read app should not flush credit writes")

    async def exists_transaction_with_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> bool:
        raise AssertionError("contract read app should not check credit idempotency")

    async def exists_transaction_with_source(
        self,
        *,
        source: CreditTransactionSourceKey,
    ) -> bool:
        raise AssertionError("contract read app should not check credit source")

    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        raise AssertionError("contract read app should not delete credit state")

    async def list_transactions(
        self,
        *,
        user_id: UUID,
        cursor: CreditTransactionCursor | None,
        limit: int,
    ) -> CreditTransactionListResult:
        transactions = _credit_transactions_for(user_id)
        filtered_transactions = _transactions_after_cursor(transactions, cursor)
        page_transactions = filtered_transactions[:limit]
        return CreditTransactionListResult(
            transactions=page_transactions,
            has_next=len(filtered_transactions) > limit,
            total_count=len(transactions),
        )


def create_credits_usage_contract_app(user_id: UUID = TEST_USER_ID) -> FastAPI:
    test_app = create_app(TEST_SETTINGS)
    test_app.dependency_overrides[authenticate_current_principal] = (
        _fake_authenticate_current_principal_for(user_id)
    )
    test_app.dependency_overrides[get_current_user_profile_query_use_case] = lambda: (
        CurrentUserProfileQueryUseCaseStub()
    )
    test_app.dependency_overrides[get_credit_repository] = lambda: CreditRepositoryStub()
    return test_app


def _fake_authenticate_current_principal_for(
    user_id: UUID,
) -> Callable[[Request], Awaitable[AuthenticatedPrincipal]]:
    async def authenticate(request: Request) -> AuthenticatedPrincipal:
        principal = AuthenticatedPrincipal(
            user_id=user_id,
            credentials_id=TEST_CREDENTIALS_ID,
            session_id=TEST_SESSION_ID,
            role="user",
        )
        set_current_principal(request, principal)
        return principal

    return authenticate


def _credit_transactions_for(user_id: UUID) -> tuple[CreditTransactionListItem, ...]:
    if user_id != SEEDED_CREDITS_USER_ID:
        return ()
    return (
        CreditTransactionListItem(
            transaction_id=UUID("00000000-0000-0000-0000-000000000001"),
            user_id=user_id,
            reason=CreditReason("monthlyOcrAllowance"),
            action=CreditAction.GRANT,
            amount=CreditAmount(value=12, field_name="amount"),
            created_at=datetime(2026, 6, 29, 9, 0, tzinfo=UTC),
        ),
        CreditTransactionListItem(
            transaction_id=UUID("00000000-0000-0000-0000-000000000002"),
            user_id=user_id,
            reason=CreditReason("eventOcrAllowance"),
            action=CreditAction.GRANT,
            amount=CreditAmount(value=3, field_name="amount"),
            created_at=datetime(2026, 6, 29, 9, 3, tzinfo=UTC),
        ),
        CreditTransactionListItem(
            transaction_id=UUID("00000000-0000-0000-0000-000000000003"),
            user_id=user_id,
            reason=CreditReason("ocrUsage"),
            action=CreditAction.USE,
            amount=CreditAmount(value=5, field_name="amount"),
            created_at=datetime(2026, 6, 29, 9, 5, tzinfo=UTC),
        ),
    )


def _transactions_after_cursor(
    transactions: tuple[CreditTransactionListItem, ...],
    cursor: CreditTransactionCursor | None,
) -> tuple[CreditTransactionListItem, ...]:
    if cursor is None:
        return transactions
    return tuple(
        transaction
        for transaction in transactions
        if (transaction.created_at, transaction.transaction_id)
        > (cursor.created_at, cursor.transaction_id)
    )
