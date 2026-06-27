from datetime import date
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class CreateReceiptRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "item_name": "삼성 냉장고 875L",
                    "brand_name": "삼성",
                    "payment_location": "전자랜드",
                    "payment_date": "2024-05-26",
                    "total_amount": 5137000,
                    "period_months": 24,
                    "category": "가전",
                    "memo": "OCR 결과 확인 후 저장",
                    "requires_physical_receipt": True,
                    "receipt_file_ids": ["00000000-0000-0000-0000-000000000201"],
                }
            ]
        },
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
    payment_location: str | None = Field(
        default=None,
        description="구매처 또는 결제처.",
        max_length=500,
    )
    payment_date: date = Field(description="구매일 또는 결제일.")
    total_amount: int | None = Field(
        default=None,
        description="총 결제 금액.",
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
    receipt_id: UUID = Field(description="등록된 영수증 ID.")
    item_name: str = Field(description="저장된 제품명 또는 대표 결제 항목명.")
    brand_name: str | None = Field(description="저장된 브랜드명.")
    payment_location: str | None = Field(description="저장된 구매처 또는 결제처.")
    payment_date: date = Field(description="저장된 구매일 또는 결제일.")
    total_amount: int | None = Field(description="저장된 총 결제 금액.")
    period_months: int = Field(description="저장된 무상 AS 기간.")
    expires_on: date = Field(description="서버가 계산한 무상 AS 만료일.")
    category: str | None = Field(description="저장된 대분류 카테고리.")
    memo: str | None = Field(description="저장된 사용자 메모.")
    requires_physical_receipt: bool = Field(description="실물 영수증 보관 필요 여부.")
    receipt_file_ids: list[UUID] = Field(description="연결된 영수증 파일 ID 목록.")


class CreateReceiptResponse(ReceiptResponse):
    pass


class UpdateReceiptRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "item_name": "삼성 냉장고 875L",
                    "brand_name": "삼성",
                    "payment_location": "전자랜드",
                    "payment_date": "2024-05-26",
                    "total_amount": 5137000,
                    "period_months": 24,
                    "category": "주방 가전",
                    "memo": "보증서 사진 추가",
                    "requires_physical_receipt": True,
                    "receipt_file_ids": [
                        "00000000-0000-0000-0000-000000000201",
                        "00000000-0000-0000-0000-000000000202",
                    ],
                }
            ]
        },
    )

    item_name: str | None = Field(default=None, description="제품명.", max_length=255)
    brand_name: str | None = Field(default=None, description="브랜드명.", max_length=255)
    payment_location: str | None = Field(
        default=None,
        description="구매처 또는 결제처.",
        max_length=500,
    )
    payment_date: date | None = Field(default=None, description="구매일 또는 결제일.")
    total_amount: int | None = Field(default=None, description="총 결제 금액.")
    period_months: int | None = Field(
        default=None,
        description="무상 AS 기간.",
        ge=1,
        le=60,
    )
    category: str | None = Field(default=None, description="대분류 카테고리.", max_length=100)
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
