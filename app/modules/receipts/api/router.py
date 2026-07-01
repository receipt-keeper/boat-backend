import base64
import binascii
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.core.domain.exceptions import ErrorDetail, ValidationError
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
from app.modules.receipts.domain.value_objects import ReceiptSort, ReceiptStatusFilter
from app.modules.receipts.mock import SAMPLE_RECEIPTS

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
        "로그인 사용자에게 등록된 영수증이 없으면 빈 배열을 반환한다. "
        "단, dev 환경에서는 앱 목록 화면 테스트를 위해 샘플 영수증 목록을 반환한다."
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
    query: Annotated[ReceiptListQuery, Query()],
    principal: CurrentPrincipalDep,
    query_use_case: ListReceiptsQueryUseCaseDep,
    settings: Annotated[Settings, Depends(get_request_settings)],
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
    if settings.app_env == "dev" and result.total_count == 0:
        unfiltered_result = await query_use_case.execute(
            ListReceiptsQuery(
                user_id=principal.user_id,
                status=ReceiptStatusFilter.ALL,
                sort=ReceiptSort.RECENT,
                limit=1,
            )
        )
        if unfiltered_result.total_count > 0:
            return CommonResponse(
                success=True,
                status=status.HTTP_200_OK,
                data=ReceiptListResponse(
                    receipts=[],
                    totalCount=result.total_count,
                    pagination=CursorPaginationResponse(
                        nextCursor=result.next_cursor,
                        hasNext=result.has_next,
                        limit=result.limit,
                        totalCount=result.total_count,
                    ),
                ),
            )
        return CommonResponse(
            success=True,
            status=status.HTTP_200_OK,
            data=_dev_mock_receipt_list_response(query),
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


def _dev_mock_receipt_list_response(query: ReceiptListQuery) -> ReceiptListResponse:
    filtered_receipts = _filter_dev_mock_receipts(query)
    start = _dev_mock_start_index(filtered_receipts, query.cursor, sort=query.sort)
    end = min(start + query.limit, len(filtered_receipts))
    page_items = filtered_receipts[start:end]
    has_next = end < len(filtered_receipts)
    return ReceiptListResponse(
        receipts=page_items,
        totalCount=len(filtered_receipts),
        pagination=CursorPaginationResponse(
            nextCursor=(
                _encode_dev_mock_cursor(sort=query.sort, receipt=page_items[-1])
                if has_next and page_items
                else None
            ),
            hasNext=has_next,
            limit=query.limit,
            totalCount=len(filtered_receipts),
        ),
    )


def _filter_dev_mock_receipts(query: ReceiptListQuery) -> list[ReceiptResponse]:
    receipts = list(SAMPLE_RECEIPTS)
    if query.status is not ReceiptStatusFilter.ALL:
        receipts = [receipt for receipt in receipts if _matches_status(receipt, query.status)]
    if query.category is not None:
        receipts = [receipt for receipt in receipts if receipt.category == query.category]
    if query.q is not None:
        keyword = query.q.casefold()
        receipts = [
            receipt
            for receipt in receipts
            if any(
                keyword in value.casefold()
                for value in (
                    receipt.item_name,
                    receipt.brand_name,
                    receipt.payment_location,
                    receipt.memo,
                )
                if value is not None
            )
        ]
    return sorted(
        receipts,
        key=_dev_mock_sort_key(query.sort),
        reverse=_dev_mock_sort_reverse(query.sort),
    )


def _dev_mock_start_index(
    receipts: list[ReceiptResponse],
    cursor: str | None,
    *,
    sort: ReceiptSort,
) -> int:
    if cursor is None:
        return 0
    cursor_receipt_id = _decode_dev_mock_cursor_receipt_id(cursor, sort=sort)
    for index, receipt in enumerate(receipts):
        if receipt.receipt_id == cursor_receipt_id:
            return index + 1
    raise _invalid_dev_mock_cursor_error()


def _encode_dev_mock_cursor(*, sort: ReceiptSort, receipt: ReceiptResponse) -> str:
    payload = {
        "sort": sort.value,
        "value": _dev_mock_cursor_value(sort, receipt).isoformat(),
        "id": str(receipt.receipt_id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return encoded.rstrip("=")


def _decode_dev_mock_cursor_receipt_id(cursor: str, *, sort: ReceiptSort) -> UUID:
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor).decode("utf-8"))
        cursor_sort = ReceiptSort(payload["sort"])
        if cursor_sort != sort:
            raise ValueError("cursor sort mismatch")
        cursor_receipt_id = payload["id"]
        if not isinstance(cursor_receipt_id, str):
            raise ValueError("cursor id must be a string")
        return UUID(cursor_receipt_id)
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exception:
        raise _invalid_dev_mock_cursor_error() from exception


def _invalid_dev_mock_cursor_error() -> ValidationError:
    return ValidationError([ErrorDetail(field="cursor", message="유효하지 않은 커서입니다.")])


def _dev_mock_cursor_value(sort: ReceiptSort, receipt: ReceiptResponse) -> Any:
    if sort is ReceiptSort.EXPIRES_ON:
        return receipt.expires_on
    if sort is ReceiptSort.PURCHASE_DATE:
        return receipt.payment_date
    return receipt.registered_at


def _matches_status(receipt: ReceiptResponse, status_filter: ReceiptStatusFilter) -> bool:
    if receipt.warranty_d_day is None:
        return status_filter is ReceiptStatusFilter.ACTIVE
    if status_filter is ReceiptStatusFilter.EXPIRED:
        return receipt.warranty_d_day < 0
    if status_filter is ReceiptStatusFilter.EXPIRING:
        return 0 <= receipt.warranty_d_day <= 30
    if status_filter is ReceiptStatusFilter.ACTIVE:
        return receipt.warranty_d_day > 30
    return True


def _dev_mock_sort_key(sort: ReceiptSort) -> Any:
    if sort is ReceiptSort.EXPIRES_ON:
        return lambda receipt: receipt.expires_on
    if sort is ReceiptSort.PURCHASE_DATE:
        return lambda receipt: receipt.payment_date
    return lambda receipt: receipt.registered_at


def _dev_mock_sort_reverse(sort: ReceiptSort) -> bool:
    return sort is not ReceiptSort.EXPIRES_ON


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
            supportUrl=resolve_service_center_url(
                brand_name=result.brand_name,
                item_name=result.item_name,
            ),
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
        subCategory=receipt.sub_category,
        memo=receipt.memo,
        requiresPhysicalReceipt=receipt.requires_physical_receipt,
        receiptFileIds=list(receipt.receipt_file_ids),
        imageUrl=None,
        warrantyDDay=receipt.warranty_d_day,
        serialNumber=None,
        supportUrl=resolve_service_center_url(
            brand_name=receipt.brand_name,
            item_name=receipt.item_name,
        ),
        registeredAt=receipt.registered_at,
    )
