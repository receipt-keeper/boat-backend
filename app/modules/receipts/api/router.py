from typing import Any

from fastapi import APIRouter, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.receipts.api.schemas import CreateReceiptRequest, CreateReceiptResponse
from app.modules.receipts.application.commands.create_receipt.command import CreateReceiptCommand
from app.modules.receipts.dependencies import CreateReceiptCommandUseCaseDep

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 — 요청 형식 오류 또는 도메인 검증 실패",
    },
}

router = APIRouter(
    prefix="/receipts",
    tags=["receipts"],
    responses=_ERROR_RESPONSES,
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CommonResponse[CreateReceiptResponse],
    summary="영수증 등록",
    description="OCR 결과를 사용자가 수정한 최종값 또는 수동 입력값으로 영수증을 등록한다.",
)
async def create_receipt(
    request: CreateReceiptRequest,
    principal: CurrentPrincipalDep,
    command_use_case: CreateReceiptCommandUseCaseDep,
) -> CommonResponse[CreateReceiptResponse]:
    result = await command_use_case.execute(
        CreateReceiptCommand(
            user_id=principal.user_id,
            item_name=request.item_name,
            brand_name=request.brand_name,
            payment_location=request.payment_location,
            payment_date=request.payment_date,
            total_amount=request.total_amount,
            period_months=request.period_months,
            category=request.category,
            memo=request.memo,
            requires_physical_receipt=request.requires_physical_receipt,
            receipt_file_ids=tuple(request.receipt_file_ids),
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_201_CREATED,
        data=CreateReceiptResponse(
            receipt_id=result.receipt_id,
            item_name=result.item_name,
            brand_name=result.brand_name,
            payment_location=result.payment_location,
            payment_date=result.payment_date,
            total_amount=result.total_amount,
            period_months=result.period_months,
            expires_on=result.expires_on,
            category=result.category,
            memo=result.memo,
            requires_physical_receipt=result.requires_physical_receipt,
            receipt_file_ids=list(result.receipt_file_ids),
        ),
    )
