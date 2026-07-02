from datetime import date, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel, CursorPaginationResponse
from app.modules.receipts.api.examples import (
    CREATE_RECEIPT_REQUEST_EXAMPLES,
    UPDATE_RECEIPT_REQUEST_EXAMPLES,
)
from app.modules.receipts.domain.value_objects import ReceiptSort, ReceiptStatusFilter


class ReceiptListQuery(AppBaseModel):
    model_config = ConfigDict(frozen=True)

    status: ReceiptStatusFilter = Field(
        default=ReceiptStatusFilter.ALL,
        description=(
            "무상 AS 상태 필터. all은 전체, active는 서비스 가능, "
            "expiring은 만료 임박, expired는 만료된 영수증이다."
        ),
    )
    sort: ReceiptSort = Field(
        default=ReceiptSort.RECENT,
        description=(
            "정렬 기준. recent는 등록일 내림차순, expiresOn은 무상 AS 만료일 오름차순, "
            "purchaseDate는 구매일 내림차순이다."
        ),
    )
    limit: int = Field(default=20, description="응답할 최대 영수증 수.", ge=1, le=50)
    cursor: str | None = Field(
        default=None,
        description="다음 목록 조회용 커서. 첫 조회에서는 보내지 않는다.",
        min_length=1,
        max_length=200,
    )
    category: str | None = Field(
        default=None,
        description="카테고리 완전 일치 필터.",
        min_length=1,
        max_length=100,
    )
    q: str | None = Field(
        default=None,
        description="제품명, 브랜드명, 구매처, 메모에서 찾을 검색어.",
        min_length=1,
        max_length=30,
    )


class CreateReceiptRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=cast(dict[str, Any], {"examples": CREATE_RECEIPT_REQUEST_EXAMPLES}),
    )

    item_name: str = Field(
        description="제품명 또는 대표 결제 항목명.",
        max_length=255,
    )
    brand_name: str | None = Field(
        default=None,
        description="브랜드명.",
        max_length=255,
    )
    serial_number: str | None = Field(
        default=None,
        description="시리얼 넘버. 확인되지 않으면 보내지 않거나 null로 보낸다.",
        max_length=255,
    )
    payment_location: str | None = Field(
        default=None,
        description="구매처 또는 결제처.",
        max_length=500,
    )
    payment_date: date = Field(description="구매일 또는 결제일.")
    total_amount: int | None = Field(
        default=None,
        description="총 결제 금액. 전달하는 경우 0 이상이어야 한다.",
    )
    period_months: int | None = Field(
        default=None,
        description="무상 AS 기간. 미전달 시 12개월 기본값을 적용한다.",
        ge=1,
        le=60,
    )
    category: str | None = Field(
        default=None,
        description="대분류 카테고리.",
        max_length=100,
    )
    sub_category: str | None = Field(
        default=None,
        description="소분류 대표 기기명.",
        max_length=100,
    )
    memo: str | None = Field(
        default=None,
        description="사용자 메모.",
        max_length=1000,
    )
    requires_physical_receipt: bool = Field(
        default=False,
        description="AS 접수 시 실물 영수증 보관이 필요한지 여부.",
    )
    receipt_file_ids: list[UUID] = Field(
        description=(
            "이미 업로드된 본인 영수증 파일 ID 목록. "
            "저장된 영수증은 항상 1장 이상 5장 이하의 이미지가 필요하다."
        ),
        min_length=1,
        max_length=5,
    )


class ReceiptResponse(AppBaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receipt_id: UUID = Field(alias="receiptId", description="등록된 영수증 ID.")
    item_name: str = Field(alias="itemName", description="저장된 제품명 또는 대표 결제 항목명.")
    brand_name: str | None = Field(alias="brandName", description="저장된 브랜드명.")
    payment_location: str | None = Field(
        alias="paymentLocation", description="저장된 구매처 또는 결제처."
    )
    payment_date: date = Field(alias="paymentDate", description="저장된 구매일 또는 결제일.")
    total_amount: int | None = Field(alias="totalAmount", description="저장된 총 결제 금액.")
    period_months: int = Field(alias="periodMonths", description="저장된 무상 AS 기간.")
    expires_on: date = Field(alias="expiresOn", description="서버가 계산한 무상 AS 만료일.")
    category: str | None = Field(description="저장된 대분류 카테고리.")
    sub_category: str | None = Field(alias="subCategory", description="저장된 소분류 대표 기기명.")
    memo: str | None = Field(description="저장된 사용자 메모.")
    requires_physical_receipt: bool = Field(
        alias="requiresPhysicalReceipt", description="실물 영수증 보관 필요 여부."
    )
    receipt_file_ids: list[UUID] = Field(
        alias="receiptFileIds", description="연결된 영수증 파일 ID 목록."
    )
    image_url: str | None = Field(default=None, alias="imageUrl", description="대표 이미지 URL.")
    warranty_d_day: int | None = Field(
        default=None,
        alias="warrantyDDay",
        description="무상 AS 만료일까지 남은 일수. 만료된 경우 음수.",
    )
    serial_number: str | None = Field(
        default=None, alias="serialNumber", description="시리얼 넘버."
    )
    support_url: str | None = Field(
        default=None, alias="supportUrl", description="서비스센터 검색 링크."
    )
    registered_at: datetime | None = Field(
        default=None, alias="registeredAt", description="등록 시각."
    )


class CreateReceiptResponse(ReceiptResponse):
    pass


class ReceiptListResponse(AppBaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receipts: list[ReceiptResponse] = Field(description="영수증 목록.")
    total_count: int = Field(alias="totalCount", description="필터 조건에 맞는 전체 영수증 수.")
    pagination: CursorPaginationResponse = Field(description="커서 기반 목록 정보.")


class UpdateReceiptRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=cast(dict[str, Any], {"examples": UPDATE_RECEIPT_REQUEST_EXAMPLES}),
    )

    item_name: str | None = Field(default=None, description="제품명.", max_length=255)
    brand_name: str | None = Field(default=None, description="브랜드명.", max_length=255)
    serial_number: str | None = Field(
        default=None,
        description="시리얼 넘버. null로 보내면 저장된 값을 비운다.",
        max_length=255,
    )
    payment_location: str | None = Field(
        default=None,
        description="구매처 또는 결제처.",
        max_length=500,
    )
    payment_date: date | None = Field(default=None, description="구매일 또는 결제일.")
    total_amount: int | None = Field(
        default=None,
        description="총 결제 금액. 전달하는 경우 0 이상이어야 한다.",
    )
    period_months: int | None = Field(
        default=None,
        description="무상 AS 기간.",
        ge=1,
        le=60,
    )
    category: str | None = Field(default=None, description="대분류 카테고리.", max_length=100)
    sub_category: str | None = Field(
        default=None,
        description="소분류 대표 기기명.",
        max_length=100,
    )
    memo: str | None = Field(default=None, description="사용자 메모.", max_length=1000)
    requires_physical_receipt: bool | None = Field(
        default=None,
        description="AS 접수 시 실물 영수증 보관이 필요한지 여부.",
    )
    receipt_file_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "수정 후 영수증에 연결할 업로드 파일 ID 목록. "
            "보내는 경우 최종 목록은 1장 이상 5장 이하여야 한다."
        ),
        min_length=1,
        max_length=5,
    )
