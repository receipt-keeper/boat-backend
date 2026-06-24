from datetime import date

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class ReceiptOcrRequest(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "file_id": "01J0Z4E4R6R9N8J8X4QG2R7V9A",
                }
            ]
        }
    )

    file_id: str = Field(
        description="파일 업로드 API로 저장된 영수증 이미지 파일 ID.",
    )


class ReceiptOcrResultResponse(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "item_name": "삼성 냉장고 875L",
                    "brand_name": "삼성",
                    "payment_location": "전자랜드",
                    "payment_date": "2024-05-26",
                    "total_amount": 5137000,
                    "period_months": 12,
                    "expires_on": "2025-05-26",
                    "needs_review": True,
                    "warnings": ["무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다."],
                }
            ]
        }
    )

    item_name: str = Field(description="대표 결제 항목명")
    brand_name: str | None = Field(description="브랜드명")
    payment_location: str | None = Field(description="구매처")
    payment_date: date = Field(description="구매일")
    total_amount: int | None = Field(description="총 결제 금액")
    period_months: int = Field(description="무상 AS 기간. 인식 실패 시 12개월 기본값")
    expires_on: date = Field(description="무상 AS 만료일")
    needs_review: bool = Field(description="기본값 적용 등 사용자 확인이 필요한지 여부")
    warnings: list[str] = Field(description="사용자 확인이 필요한 항목 안내")
