from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse, CursorPaginationResponse
from app.modules.receipts.api.schemas import (
    CreateReceiptRequest,
    CreateReceiptResponse,
    ReceiptListQuery,
    ReceiptListResponse,
    ReceiptResponse,
    UpdateReceiptRequest,
)
from app.modules.receipts.application.commands.create_receipt.command import CreateReceiptCommand
from app.modules.receipts.application.commands.delete_receipt.command import DeleteReceiptCommand
from app.modules.receipts.application.commands.update_receipt.command import UpdateReceiptCommand
from app.modules.receipts.application.queries.get_receipt.query import GetReceiptQuery
from app.modules.receipts.application.queries.list_receipts.query import ListReceiptsQuery
from app.modules.receipts.application.read_models.receipt import ReceiptReadModel
from app.modules.receipts.dependencies import (
    CreateReceiptCommandUseCaseDep,
    DeleteReceiptCommandUseCaseDep,
    GetReceiptQueryUseCaseDep,
    ListReceiptsQueryUseCaseDep,
    UpdateReceiptCommandUseCaseDep,
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
    principal: CurrentPrincipalDep,
    query_use_case: ListReceiptsQueryUseCaseDep,
) -> CommonResponse[ReceiptListResponse]:
    result = await query_use_case.execute(
        ListReceiptsQuery(
            user_id=principal.user_id,
            status=query.status,
            sort=query.sort,
            limit=query.limit,
            cursor=query.cursor,
            category=query.category,
            q=query.q,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=ReceiptListResponse(
            receipts=[_receipt_response(receipt) for receipt in result.receipts],
            totalCount=result.total_count,
            pagination=CursorPaginationResponse(
                nextCursor=result.next_cursor,
                hasNext=result.has_next,
                limit=result.limit,
                totalCount=result.total_count,
            ),
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
async def get_receipt(
    receipt_id: UUID,
    principal: CurrentPrincipalDep,
    query_use_case: GetReceiptQueryUseCaseDep,
) -> CommonResponse[ReceiptResponse]:
    result = await query_use_case.execute(
        GetReceiptQuery(user_id=principal.user_id, receipt_id=receipt_id)
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=_receipt_response(result),
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
    principal: CurrentPrincipalDep,
    command_use_case: UpdateReceiptCommandUseCaseDep,
) -> CommonResponse[ReceiptResponse]:
    result = await command_use_case.execute(
        UpdateReceiptCommand(
            user_id=principal.user_id,
            receipt_id=receipt_id,
            updated_fields=frozenset(request.model_fields_set),
            item_name=request.item_name,
            brand_name=request.brand_name,
            payment_location=request.payment_location,
            payment_date=request.payment_date,
            total_amount=request.total_amount,
            period_months=request.period_months,
            category=request.category,
            memo=request.memo,
            requires_physical_receipt=request.requires_physical_receipt,
            receipt_file_ids=(
                None if request.receipt_file_ids is None else tuple(request.receipt_file_ids)
            ),
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=_receipt_response(result),
    )


@router.delete(
    "/{receipt_id}",
    response_model=CommonResponse[None],
    summary="영수증 삭제",
    description=(
        "등록된 영수증과 제품 조회 데이터를 삭제한다. "
        "연결 해제된 파일의 실제 스토리지 삭제는 파일 정리 작업에서 처리한다."
    ),
)
async def delete_receipt(
    receipt_id: UUID,
    principal: CurrentPrincipalDep,
    command_use_case: DeleteReceiptCommandUseCaseDep,
) -> CommonResponse[None]:
    await command_use_case.execute(
        DeleteReceiptCommand(user_id=principal.user_id, receipt_id=receipt_id)
    )
    return CommonResponse(success=True, status=status.HTTP_200_OK, data=None)


def _receipt_response(receipt: ReceiptReadModel) -> ReceiptResponse:
    return ReceiptResponse(
        receiptId=receipt.receipt_id,
        itemName=receipt.item_name,
        brandName=receipt.brand_name,
        paymentLocation=receipt.payment_location,
        paymentDate=receipt.payment_date,
        totalAmount=receipt.total_amount,
        periodMonths=receipt.period_months,
        expiresOn=receipt.expires_on,
        category=receipt.category,
        memo=receipt.memo,
        requiresPhysicalReceipt=receipt.requires_physical_receipt,
        receiptFileIds=list(receipt.receipt_file_ids),
        imageUrl=None,
        warrantyDDay=receipt.warranty_d_day,
        serialNumber=None,
        supportUrl=None,
        registeredAt=receipt.registered_at,
    )
