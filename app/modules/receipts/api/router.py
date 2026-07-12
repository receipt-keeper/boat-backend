from collections.abc import Iterable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse, CursorPaginationResponse
from app.modules.receipts.api.examples import (
    CREATE_RECEIPT_REQUEST_OPENAPI_EXAMPLES,
    CREATE_RECEIPT_RESPONSE_EXAMPLE,
    DELETE_RECEIPT_RESPONSE_EXAMPLE,
    EMPTY_RECEIPT_LIST_RESPONSE_EXAMPLE,
    GET_RECEIPT_RESPONSE_EXAMPLE,
    RECEIPT_LIST_RESPONSE_EXAMPLE,
    UPDATE_RECEIPT_REQUEST_OPENAPI_EXAMPLES,
    UPDATE_RECEIPT_RESPONSE_EXAMPLE,
)
from app.modules.receipts.api.schemas import (
    CreateReceiptRequest,
    CreateReceiptResponse,
    ReceiptFileResponse,
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
from app.modules.receipts.domain.service_centers import resolve_service_center_url

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
    description=(
        "등록된 영수증을 무상 AS 상태, 카테고리, 검색어 조건에 맞춰 반환한다. "
        "로그인 사용자에게 등록된 영수증이 없으면 빈 배열을 반환한다."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "영수증 목록 조회 성공",
            "content": {
                "application/json": {
                    "examples": {
                        "with_receipts": {
                            "summary": "등록된 영수증이 있는 경우",
                            "value": RECEIPT_LIST_RESPONSE_EXAMPLE,
                        },
                        "empty": {
                            "summary": "등록된 영수증이 없는 경우",
                            "value": EMPTY_RECEIPT_LIST_RESPONSE_EXAMPLE,
                        },
                    }
                }
            },
        }
    },
)
async def list_receipts(
    http_request: Request,
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
            receipts=[_receipt_response(http_request, receipt) for receipt in result.receipts],
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
    openapi_extra={
        "requestBody": {
            "content": {"application/json": {"examples": CREATE_RECEIPT_REQUEST_OPENAPI_EXAMPLES}}
        }
    },
    responses={
        status.HTTP_201_CREATED: {
            "description": "영수증 등록 성공",
            "content": {"application/json": {"example": CREATE_RECEIPT_RESPONSE_EXAMPLE}},
        }
    },
)
async def create_receipt(
    http_request: Request,
    request: CreateReceiptRequest,
    principal: CurrentPrincipalDep,
    command_use_case: CreateReceiptCommandUseCaseDep,
) -> CommonResponse[CreateReceiptResponse]:
    result = await command_use_case.execute(
        CreateReceiptCommand(
            user_id=principal.user_id,
            item_name=request.item_name,
            brand_name=request.brand_name,
            serial_number=request.serial_number,
            payment_location=request.payment_location,
            payment_date=request.payment_date,
            total_amount=request.total_amount,
            period_months=request.period_months,
            expires_on=request.expires_on,
            category=request.category,
            sub_category=request.sub_category,
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
            serialNumber=result.serial_number,
            paymentLocation=result.payment_location,
            paymentDate=result.payment_date,
            totalAmount=result.total_amount,
            periodMonths=result.period_months,
            expiresOn=result.expires_on,
            category=result.category,
            subCategory=result.sub_category,
            memo=result.memo,
            requiresPhysicalReceipt=result.requires_physical_receipt,
            receiptFileIds=list(result.receipt_file_ids),
            receiptFiles=_receipt_file_responses(http_request, result.receipt_file_ids),
            supportUrl=resolve_service_center_url(
                brand_name=result.brand_name,
                item_name=result.item_name,
            ),
            registeredAt=result.registered_at,
        ),
    )


@router.get(
    "/{receipt_id}",
    response_model=CommonResponse[ReceiptResponse],
    summary="영수증 상세 조회",
    description="등록된 영수증의 제품명, 구매일, 무상 AS 기간, 메모, 첨부 이미지를 반환한다.",
    responses={
        status.HTTP_200_OK: {
            "description": "영수증 상세 조회 성공",
            "content": {"application/json": {"example": GET_RECEIPT_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_receipt(
    http_request: Request,
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
        data=_receipt_response(http_request, result),
    )


@router.patch(
    "/{receipt_id}",
    response_model=CommonResponse[ReceiptResponse],
    summary="영수증 수정",
    description=(
        "영수증 기반 제품 정보와 첨부 이미지 목록을 수정한다. "
        "첨부 이미지는 수정 후에도 1장 이상 5장 이하여야 한다."
    ),
    openapi_extra={
        "requestBody": {
            "content": {"application/json": {"examples": UPDATE_RECEIPT_REQUEST_OPENAPI_EXAMPLES}}
        }
    },
    responses={
        status.HTTP_200_OK: {
            "description": "영수증 수정 성공",
            "content": {"application/json": {"example": UPDATE_RECEIPT_RESPONSE_EXAMPLE}},
        }
    },
)
async def update_receipt(
    http_request: Request,
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
            serial_number=request.serial_number,
            payment_location=request.payment_location,
            payment_date=request.payment_date,
            total_amount=request.total_amount,
            period_months=request.period_months,
            expires_on=request.expires_on,
            category=request.category,
            sub_category=request.sub_category,
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
        data=_receipt_response(http_request, result),
    )


@router.delete(
    "/{receipt_id}",
    response_model=CommonResponse[None],
    summary="영수증 삭제",
    description=(
        "등록된 영수증과 제품 조회 데이터를 삭제한다. "
        "연결 해제된 파일의 실제 스토리지 삭제는 파일 정리 작업에서 처리한다."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "영수증 삭제 성공",
            "content": {"application/json": {"example": DELETE_RECEIPT_RESPONSE_EXAMPLE}},
        }
    },
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


def _receipt_response(http_request: Request, receipt: ReceiptReadModel) -> ReceiptResponse:
    return ReceiptResponse(
        receiptId=receipt.receipt_id,
        itemName=receipt.item_name,
        brandName=receipt.brand_name,
        serialNumber=receipt.serial_number,
        paymentLocation=receipt.payment_location,
        paymentDate=receipt.payment_date,
        totalAmount=receipt.total_amount,
        periodMonths=receipt.period_months,
        expiresOn=receipt.expires_on,
        category=receipt.category,
        subCategory=receipt.sub_category,
        memo=receipt.memo,
        requiresPhysicalReceipt=receipt.requires_physical_receipt,
        receiptFileIds=list(receipt.receipt_file_ids),
        receiptFiles=_receipt_file_responses(http_request, receipt.receipt_file_ids),
        imageUrl=None,
        warrantyDDay=receipt.warranty_d_day,
        supportUrl=resolve_service_center_url(
            brand_name=receipt.brand_name,
            item_name=receipt.item_name,
        ),
        registeredAt=receipt.registered_at,
    )


def _receipt_file_responses(
    http_request: Request,
    file_ids: Iterable[UUID],
) -> list[ReceiptFileResponse]:
    return [
        ReceiptFileResponse(
            fileId=file_id,
            contentPath=_with_api_prefix(http_request, f"/files/{file_id}/content"),
        )
        for file_id in file_ids
    ]


def _with_api_prefix(http_request: Request, path: str) -> str:
    api_prefix = http_request.app.state.settings.api_prefix.rstrip("/")
    return f"{api_prefix}{path}"
