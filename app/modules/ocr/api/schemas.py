from datetime import UTC, date, datetime

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class ReceiptOcrFieldError(AppBaseModel):
    model_config = ConfigDict(populate_by_name=True)

    field: str = "file"
    file_index: int | None = Field(
        default=None,
        alias="fileIndex",
        ge=0,
        description="요청 multipart file 배열에서 인식에 실패한 이미지의 0-based 순서.",
    )
    message: str


class ReceiptOcrErrorData(AppBaseModel):
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    )
    code: str | None = None
    message: str
    path: str
    errors: list[ReceiptOcrFieldError] = Field(default_factory=list)


class ReceiptOcrResultResponse(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "item_name": "삼성 냉장고 875L",
                    "brand_name": "삼성",
                    "serial_number": "SN-20240526-001",
                    "payment_location": "전자랜드",
                    "payment_date": "2024-05-26",
                    "total_amount": 5137000,
                    "period_months": 12,
                    "expires_on": "2025-05-26",
                    "category": "주방 가전",
                    "sub_category": "냉장고",
                    "needs_review": True,
                    "warnings": ["무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다."],
                }
            ]
        }
    )

    item_name: str = Field(description="대표 결제 항목명")
    brand_name: str | None = Field(description="브랜드명")
    serial_number: str | None = Field(description="시리얼 넘버 후보값. 명확히 확인되지 않으면 null")
    payment_location: str | None = Field(description="구매처")
    payment_date: date = Field(description="구매일")
    total_amount: int | None = Field(description="총 결제 금액")
    period_months: int = Field(description="무상 AS 기간. 인식 실패 시 12개월 기본값")
    expires_on: date = Field(description="무상 AS 만료일")
    category: str | None = Field(
        description="대분류 카테고리 추천값. 사용자가 수정 후 저장할 수 있다."
    )
    sub_category: str | None = Field(
        description="소분류 대표 기기명 추천값. 사용자가 수정 후 저장할 수 있다."
    )
    needs_review: bool = Field(description="기본값 적용 등 사용자 확인이 필요한지 여부")
    warnings: list[str] = Field(description="사용자 확인이 필요한 항목 안내")
