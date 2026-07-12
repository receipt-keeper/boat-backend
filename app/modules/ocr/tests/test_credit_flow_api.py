import calendar
from collections.abc import Callable
from datetime import date
from uuid import UUID

from fastapi import Request
from httpx import AsyncClient

from app.core.http.auth import get_current_principal, set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.dependencies import get_reserve_credit_command_use_case
from app.modules.credits.domain import CreditAmount, CreditReason
from app.modules.credits.domain.exceptions import InsufficientCreditError
from app.modules.ocr.application.ports.receipt_ocr_client import (
    ExtractedReceiptOcrFields,
    ReceiptOcrImage,
)
from app.modules.ocr.tests.conftest import RecordingUseCreditCommandUseCase

_PNG_BYTES = b"\x89PNG\r\n\x1a\nreceipt-image"


class CountingReceiptOcrClient:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, *, images: tuple[ReceiptOcrImage, ...]) -> ExtractedReceiptOcrFields:
        self.calls += 1
        return ExtractedReceiptOcrFields(
            item_name="삼성 냉장고",
            brand_name="삼성",
            serial_number="SN-20240526-001",
            payment_location="전자랜드",
            payment_date=date.today(),
            total_amount=129000,
            period_months=12,
            category="주방 가전",
            sub_category="냉장고",
        )


class RejectingReserveCreditCommandUseCase:
    async def execute(self, command: UseCreditCommand) -> None:
        raise InsufficientCreditError()


async def test_receipt_ocr_endpoint_requires_authentication(client: AsyncClient) -> None:
    app.dependency_overrides.pop(authenticate_current_principal, None)
    app.dependency_overrides.pop(get_current_principal, None)

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 401
    assert body["success"] is False
    assert body["status"] == 401

    app.dependency_overrides.pop(get_current_principal, None)


async def test_receipt_ocr_endpoint_runs_router_authentication_before_principal_lookup(
    client: AsyncClient,
) -> None:
    app.dependency_overrides.pop(get_current_principal, None)

    async def authenticate(request: Request) -> AuthenticatedPrincipal:
        principal = AuthenticatedPrincipal(
            user_id=UUID("00000000-0000-0000-0000-000000000301"),
            credentials_id=UUID("00000000-0000-0000-0000-000000000302"),
            session_id=UUID("00000000-0000-0000-0000-000000000303"),
            role="user",
        )
        set_current_principal(request, principal)
        return principal

    app.dependency_overrides[authenticate_current_principal] = authenticate

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
        headers={"Authorization": "Bearer backend-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_receipt_ocr_endpoint_returns_contract_response_and_finalizes_credit(
    client: AsyncClient,
    use_recording_credit_command_use_case: RecordingUseCreditCommandUseCase,
) -> None:
    today = date.today()
    last_day = calendar.monthrange(today.year + 1, today.month)[1]
    expected_expires_on = date(today.year + 1, today.month, min(today.day, last_day))

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"] == {
        "item_name": "삼성 냉장고 875L",
        "brand_name": "삼성",
        "serial_number": "SN-20240526-001",
        "payment_location": "테스트 구매처",
        "payment_date": today.isoformat(),
        "total_amount": 129000,
        "period_months": 12,
        "expires_on": expected_expires_on.isoformat(),
        "category": "주방 가전",
        "sub_category": "냉장고",
        "needs_review": True,
        "warnings": ["무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다."],
    }
    assert len(use_recording_credit_command_use_case.commands) == 1
    finalized_command = use_recording_credit_command_use_case.commands[0]
    assert finalized_command.amount == CreditAmount(value=1, field_name="amount")
    assert finalized_command.reason is CreditReason.OCR_USAGE


async def test_receipt_ocr_endpoint_skips_provider_when_credit_is_insufficient(
    client: AsyncClient,
    override_receipt_ocr_client: Callable[[CountingReceiptOcrClient], None],
) -> None:
    ocr_client = CountingReceiptOcrClient()
    override_receipt_ocr_client(ocr_client)
    app.dependency_overrides[get_reserve_credit_command_use_case] = lambda: (
        RejectingReserveCreditCommandUseCase()
    )

    response = await client.post(
        "/api/v1/ocr",
        files={"file": ("receipt.png", _PNG_BYTES, "image/png")},
    )

    body = response.json()

    assert response.status_code == 409
    assert body["success"] is False
    assert body["status"] == 409
    assert body["data"]["code"] == "INSUFFICIENT_CREDIT"
    assert ocr_client.calls == 0
