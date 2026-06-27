from datetime import date
from typing import Annotated, Any, assert_never
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.pagination import paginate_by_cursor
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.receipts.api.schemas import (
    CreateReceiptRequest,
    CreateReceiptResponse,
    ReceiptListQuery,
    ReceiptListResponse,
    ReceiptResponse,
    UpdateReceiptRequest,
)
from app.modules.receipts.application.commands.create_receipt.command import CreateReceiptCommand
from app.modules.receipts.dependencies import CreateReceiptCommandUseCaseDep
from app.modules.receipts.domain.value_objects import ReceiptSort, ReceiptStatusFilter
from app.modules.receipts.mock import (
    SAMPLE_FILE_ID,
    SAMPLE_RECEIPTS,
    SECOND_SAMPLE_FILE_ID,
    receipt_with_id,
    sample_receipt,
)

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


@router.get(
    "",
    response_model=CommonResponse[ReceiptListResponse],
    summary="영수증 목록 조회",
    description="등록된 영수증을 무상 AS 상태, 카테고리, 검색어 조건에 맞춰 반환한다.",
)
async def list_receipts(
    query: Annotated[ReceiptListQuery, Query()],
) -> CommonResponse[ReceiptListResponse]:
    filtered_receipts = _sort_receipts(_filter_receipts(SAMPLE_RECEIPTS, query), query.sort)
    page = paginate_by_cursor(
        filtered_receipts,
        cursor=query.cursor,
        limit=query.limit,
        total_count=len(filtered_receipts),
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=ReceiptListResponse(
            receipts=page.items,
            totalCount=len(filtered_receipts),
            pagination=page.pagination,
        ),
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
            receiptId=result.receipt_id,
            itemName=result.item_name,
            brandName=result.brand_name,
            paymentLocation=result.payment_location,
            paymentDate=result.payment_date,
            totalAmount=result.total_amount,
            periodMonths=result.period_months,
            expiresOn=result.expires_on,
            category=result.category,
            memo=result.memo,
            requiresPhysicalReceipt=result.requires_physical_receipt,
            receiptFileIds=list(result.receipt_file_ids),
        ),
    )


@router.get(
    "/{receipt_id}",
    response_model=CommonResponse[ReceiptResponse],
    summary="영수증 상세 조회",
    description="등록된 영수증의 제품명, 구매일, 무상 AS 기간, 메모, 첨부 이미지를 반환한다.",
)
async def get_receipt(receipt_id: UUID) -> CommonResponse[ReceiptResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=receipt_with_id(receipt_id),
    )


@router.patch(
    "/{receipt_id}",
    response_model=CommonResponse[ReceiptResponse],
    summary="영수증 수정",
    description=(
        "영수증 기반 제품 정보와 첨부 이미지 목록을 수정한다. "
        "첨부 이미지는 수정 후에도 1장 이상 5장 이하여야 한다."
    ),
)
async def update_receipt(
    receipt_id: UUID,
    request: UpdateReceiptRequest,
) -> CommonResponse[ReceiptResponse]:
    receipt_file_ids = request.receipt_file_ids or [SAMPLE_FILE_ID, SECOND_SAMPLE_FILE_ID]
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=sample_receipt(
            receipt_id=receipt_id,
            item_name=request.item_name or "삼성 냉장고 875L",
            brand_name=request.brand_name,
            payment_location=request.payment_location,
            payment_date=request.payment_date or date(2024, 5, 26),
            total_amount=request.total_amount,
            period_months=request.period_months or 24,
            category=request.category,
            memo=request.memo,
            requires_physical_receipt=(
                request.requires_physical_receipt
                if request.requires_physical_receipt is not None
                else True
            ),
            receipt_file_ids=receipt_file_ids,
        ),
    )


@router.delete(
    "/{receipt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="영수증 삭제",
    description=(
        "등록된 영수증과 제품 조회 데이터를 삭제한다. "
        "연결 해제된 파일의 실제 스토리지 삭제는 파일 정리 작업에서 처리한다."
    ),
)
async def delete_receipt(_receipt_id: UUID) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _filter_receipts(
    receipts: tuple[ReceiptResponse, ...],
    query: ReceiptListQuery,
) -> list[ReceiptResponse]:
    filtered = [receipt for receipt in receipts if _matches_status(receipt, query.status)]
    if query.category is not None:
        filtered = [receipt for receipt in filtered if receipt.category == query.category]
    if query.q is not None:
        keyword = query.q.casefold()
        filtered = [receipt for receipt in filtered if _contains_keyword(receipt, keyword)]
    return filtered


def _matches_status(
    receipt: ReceiptResponse,
    status_filter: ReceiptStatusFilter,
) -> bool:
    d_day = receipt.warranty_d_day
    match status_filter:
        case ReceiptStatusFilter.ALL:
            return True
        case ReceiptStatusFilter.ACTIVE:
            return d_day is not None and d_day > 30
        case ReceiptStatusFilter.EXPIRING:
            return d_day is not None and 0 <= d_day <= 30
        case ReceiptStatusFilter.EXPIRED:
            return d_day is not None and d_day < 0
        case unreachable:
            assert_never(unreachable)


def _contains_keyword(receipt: ReceiptResponse, keyword: str) -> bool:
    searchable_values = (
        receipt.item_name,
        receipt.brand_name,
        receipt.payment_location,
        receipt.memo,
    )
    return any(value is not None and keyword in value.casefold() for value in searchable_values)


def _sort_receipts(
    receipts: list[ReceiptResponse],
    sort: ReceiptSort,
) -> list[ReceiptResponse]:
    match sort:
        case ReceiptSort.RECENT:
            return sorted(
                receipts,
                key=lambda receipt: receipt.registered_at or date.min,
                reverse=True,
            )
        case ReceiptSort.EXPIRES_ON:
            return sorted(receipts, key=lambda receipt: receipt.expires_on)
        case ReceiptSort.PURCHASE_DATE:
            return sorted(receipts, key=lambda receipt: receipt.payment_date, reverse=True)
        case unreachable:
            assert_never(unreachable)
