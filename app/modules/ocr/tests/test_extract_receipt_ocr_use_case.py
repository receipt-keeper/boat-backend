from dataclasses import dataclass
from datetime import date
from uuid import UUID

import pytest

from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.domain import CreditAmount, CreditReason
from app.modules.ocr.application.commands.extract_receipt_ocr.command import (
    ExtractReceiptOcrCommand,
)
from app.modules.ocr.application.commands.extract_receipt_ocr.use_case import (
    ExtractReceiptOcrCommandUseCase,
)
from app.modules.ocr.application.ports.receipt_ocr_client import ExtractedReceiptOcrFields
from app.modules.ocr.domain.exceptions import ReceiptImageUnreadableError
from tests.support.unit_of_work import FakeUnitOfWork

USER_ID = UUID("00000000-0000-0000-0000-000000000301")


@dataclass(slots=True)
class FakeUseCreditCommandUseCase:
    commands: list[UseCreditCommand]

    async def execute(self, command: UseCreditCommand) -> None:
        self.commands.append(command)


@dataclass(slots=True)
class ReadableReceiptOcrClient:
    async def extract(
        self, *, image_content: bytes, content_type: str
    ) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name="삼성 냉장고",
            brand_name="삼성",
            serial_number="SN-20240526-001",
            payment_location="전자랜드",
            payment_date=date(2026, 7, 1),
            total_amount=129000,
            period_months=12,
            category="주방 가전",
            sub_category="냉장고",
        )


class UnreadableReceiptOcrClient:
    async def extract(
        self, *, image_content: bytes, content_type: str
    ) -> ExtractedReceiptOcrFields:
        return ExtractedReceiptOcrFields(
            item_name=None,
            brand_name=None,
            serial_number=None,
            payment_location=None,
            payment_date=None,
            total_amount=None,
            period_months=None,
            category=None,
            sub_category=None,
        )


class FailingReceiptOcrClient:
    async def extract(
        self, *, image_content: bytes, content_type: str
    ) -> ExtractedReceiptOcrFields:
        raise RuntimeError("ocr provider failed")


@dataclass(slots=True)
class FailingUseCreditCommandUseCase:
    commands: list[UseCreditCommand]

    async def execute(self, command: UseCreditCommand) -> None:
        self.commands.append(command)
        raise RuntimeError("finalize credit failed")


async def test_extract_receipt_ocr_use_case_consumes_credit_after_success() -> None:
    # Given: OCR provider가 읽을 수 있는 결과를 반환한다.
    reserve_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    finalize_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    unit_of_work = FakeUnitOfWork()
    use_case = ExtractReceiptOcrCommandUseCase(
        ocr_client=ReadableReceiptOcrClient(),
        reserve_credit_command_use_case=reserve_credit_use_case,
        finalize_credit_usage_command_use_case=finalize_credit_use_case,
        unit_of_work=unit_of_work,
    )

    # When: 인증 사용자 기준 OCR 분석을 실행한다.
    result = await use_case.execute(
        ExtractReceiptOcrCommand(
            user_id=USER_ID,
            image_content=b"image",
            content_type="image/png",
        )
    )

    # Then: OCR 결과가 만들어진 뒤 OCR 사용 크레딧 1회가 차감된다.
    assert result.item_name.value == "삼성 냉장고"
    expected_command = UseCreditCommand(
        user_id=USER_ID,
        amount=CreditAmount(value=1, field_name="amount"),
        reason=CreditReason.OCR_USAGE,
    )
    assert reserve_credit_use_case.commands == [expected_command]
    assert finalize_credit_use_case.commands == [
        UseCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=1, field_name="amount"),
            reason=CreditReason.OCR_USAGE,
        )
    ]


async def test_extract_receipt_ocr_use_case_does_not_consume_credit_when_unreadable() -> None:
    # Given: OCR provider가 읽을 수 없는 결과를 반환한다.
    reserve_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    finalize_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    unit_of_work = FakeUnitOfWork()
    use_case = ExtractReceiptOcrCommandUseCase(
        ocr_client=UnreadableReceiptOcrClient(),
        reserve_credit_command_use_case=reserve_credit_use_case,
        finalize_credit_usage_command_use_case=finalize_credit_use_case,
        unit_of_work=unit_of_work,
    )

    # When/Then: 분석 실패는 크레딧 차감 없이 전파된다.
    with pytest.raises(ReceiptImageUnreadableError):
        await use_case.execute(
            ExtractReceiptOcrCommand(
                user_id=USER_ID,
                image_content=b"image",
                content_type="image/png",
            )
        )

    assert reserve_credit_use_case.commands == [
        UseCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=1, field_name="amount"),
            reason=CreditReason.OCR_USAGE,
        )
    ]
    assert finalize_credit_use_case.commands == []
    assert unit_of_work.rollback_count == 1


async def test_extract_receipt_ocr_use_case_rolls_back_when_provider_fails() -> None:
    reserve_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    finalize_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    unit_of_work = FakeUnitOfWork()
    use_case = ExtractReceiptOcrCommandUseCase(
        ocr_client=FailingReceiptOcrClient(),
        reserve_credit_command_use_case=reserve_credit_use_case,
        finalize_credit_usage_command_use_case=finalize_credit_use_case,
        unit_of_work=unit_of_work,
    )

    with pytest.raises(RuntimeError, match="ocr provider failed"):
        await use_case.execute(
            ExtractReceiptOcrCommand(
                user_id=USER_ID,
                image_content=b"image",
                content_type="image/png",
            )
        )

    assert reserve_credit_use_case.commands == [
        UseCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=1, field_name="amount"),
            reason=CreditReason.OCR_USAGE,
        )
    ]
    assert finalize_credit_use_case.commands == []
    assert unit_of_work.rollback_count == 1


async def test_extract_receipt_ocr_use_case_rolls_back_when_finalize_fails() -> None:
    reserve_credit_use_case = FakeUseCreditCommandUseCase(commands=[])
    finalize_credit_use_case = FailingUseCreditCommandUseCase(commands=[])
    unit_of_work = FakeUnitOfWork()
    use_case = ExtractReceiptOcrCommandUseCase(
        ocr_client=ReadableReceiptOcrClient(),
        reserve_credit_command_use_case=reserve_credit_use_case,
        finalize_credit_usage_command_use_case=finalize_credit_use_case,
        unit_of_work=unit_of_work,
    )

    with pytest.raises(RuntimeError, match="finalize credit failed"):
        await use_case.execute(
            ExtractReceiptOcrCommand(
                user_id=USER_ID,
                image_content=b"image",
                content_type="image/png",
            )
        )

    expected_command = UseCreditCommand(
        user_id=USER_ID,
        amount=CreditAmount(value=1, field_name="amount"),
        reason=CreditReason.OCR_USAGE,
    )
    assert reserve_credit_use_case.commands == [expected_command]
    assert finalize_credit_use_case.commands == [expected_command]
    assert unit_of_work.rollback_count == 1
