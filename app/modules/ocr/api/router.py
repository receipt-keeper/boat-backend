from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.files.api.upload_validation import read_and_validate_uploads
from app.modules.ocr.api.schemas import ReceiptOcrResultResponse
from app.modules.ocr.api.upload_policy import RECEIPT_OCR_UPLOAD_POLICY
from app.modules.ocr.dependencies import ReceiptOcrServiceDep

_UNREADABLE_RECEIPT_MESSAGE = (
    "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요."
)
_SUCCESS_EXAMPLE = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": {
        "item_name": "삼성 냉장고 875L",
        "brand_name": "삼성",
        "payment_location": "전자랜드",
        "payment_date": "2024-05-26",
        "total_amount": 5137000,
        "period_months": 12,
        "expires_on": "2025-05-26",
        "category": "가전",
        "needs_review": True,
        "warnings": ["무상 AS 기간을 찾지 못해 12개월 기본값을 적용했습니다."],
    },
}
_UNREADABLE_RECEIPT_EXAMPLE = {
    "success": False,
    "status": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "data": {
        "timestamp": "2026-06-21T00:00:00",
        "message": "입력값이 올바르지 않습니다.",
        "path": "/api/v1/ocr",
        "errors": [
            {
                "field": "file",
                "message": _UNREADABLE_RECEIPT_MESSAGE,
            }
        ],
    },
}
_PROVIDER_UNAVAILABLE_EXAMPLE = {
    "success": False,
    "status": status.HTTP_503_SERVICE_UNAVAILABLE,
    "data": {
        "timestamp": "2026-06-21T00:00:00",
        "message": "OCR 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        "path": "/api/v1/ocr",
        "errors": [],
    },
}

router = APIRouter(
    prefix="/ocr",
    tags=["ocr"],
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": CommonResponse[ApiErrorData],
            "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": CommonResponse[ApiErrorData],
            "description": "외부 OCR 서비스 일시 사용 불가",
        },
    },
)


@router.post(
    "",
    summary="영수증 OCR 분석",
    description=(
        "multipart/form-data로 전달된 영수증 이미지를 저장하지 않고 분석만 수행한다. "
        "대표 결제 항목, 브랜드, 구매처, 구매일, 금액, AS 기간, 대분류 카테고리 후보를 추출한다. "
        "영수증 원본 파일 보관 및 연결은 receipts 저장 API의 receipt_file_ids에서 처리한다."
    ),
    response_model=CommonResponse[ReceiptOcrResultResponse],
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "examples": {
                        "receipt_image": {
                            "summary": "영수증 이미지 분석",
                            "value": {"file": "receipt-1.png"},
                        }
                    }
                }
            }
        }
    },
    responses={
        status.HTTP_200_OK: {
            "description": "OCR 분석 성공",
            "content": {"application/json": {"example": _SUCCESS_EXAMPLE}},
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "영수증 이미지 인식 실패",
            "content": {"application/json": {"example": _UNREADABLE_RECEIPT_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "외부 OCR 서비스 일시 사용 불가",
            "content": {"application/json": {"example": _PROVIDER_UNAVAILABLE_EXAMPLE}},
        },
    },
)
async def extract_receipt_ocr(
    files: Annotated[
        list[UploadFile],
        File(
            alias="file",
            description=(
                "분석할 영수증 이미지 파일. 이 API에서는 파일을 저장하지 않으며 1개만 허용한다."
            ),
        ),
    ],
    service: ReceiptOcrServiceDep,
) -> CommonResponse[ReceiptOcrResultResponse]:
    validated_upload = (
        await read_and_validate_uploads(
            files=files,
            policy=RECEIPT_OCR_UPLOAD_POLICY,
        )
    )[0]
    result = await service.extract_receipt(
        image_content=validated_upload.content,
        content_type=validated_upload.content_type,
    )

    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=ReceiptOcrResultResponse(
            item_name=result.item_name.value,
            brand_name=result.brand_name.value if result.brand_name is not None else None,
            payment_location=(
                result.payment_location.value if result.payment_location is not None else None
            ),
            payment_date=result.payment_date.value,
            total_amount=result.total_amount.value if result.total_amount is not None else None,
            period_months=result.period_months.value,
            expires_on=result.expires_on,
            category=result.category,
            needs_review=bool(result.warnings),
            warnings=list(result.warnings),
        ),
    )
