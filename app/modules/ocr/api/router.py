import logging
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.core.domain.exceptions import ValidationError
from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.files.api.upload_validation import read_and_validate_uploads
from app.modules.ocr.api.schemas import ReceiptOcrErrorData, ReceiptOcrResultResponse
from app.modules.ocr.api.upload_policy import RECEIPT_OCR_UPLOAD_POLICY
from app.modules.ocr.application.commands.extract_receipt_ocr.command import (
    ExtractReceiptOcrCommand,
)
from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrImage
from app.modules.ocr.dependencies import ExtractReceiptOcrCommandUseCaseDep

logger = logging.getLogger(__name__)

_UNREADABLE_RECEIPT_MESSAGE = (
    "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요."
)
_SUCCESS_EXAMPLE = {
    "success": True,
    "status": status.HTTP_200_OK,
    "data": {
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
                "fileIndex": 1,
                "message": _UNREADABLE_RECEIPT_MESSAGE,
            }
        ],
    },
}
_INVALID_UPLOAD_EXAMPLE = {
    "success": False,
    "status": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "data": {
        "timestamp": "2026-06-21T00:00:00",
        "message": "입력값이 올바르지 않습니다.",
        "path": "/api/v1/ocr",
        "errors": [
            {
                "field": "files",
                "message": "파일은 최대 5개까지 업로드할 수 있습니다.",
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
_INSUFFICIENT_CREDIT_EXAMPLE = {
    "success": False,
    "status": status.HTTP_409_CONFLICT,
    "data": {
        "timestamp": "2026-06-21T00:00:00",
        "message": "사용 가능한 크레딧이 부족합니다.",
        "path": "/api/v1/ocr",
        "errors": [],
    },
}

router = APIRouter(
    prefix="/ocr",
    tags=["ocr"],
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": CommonResponse[ReceiptOcrErrorData],
            "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
        },
        status.HTTP_409_CONFLICT: {
            "model": CommonResponse[ApiErrorData],
            "description": "OCR 분석에 사용할 크레딧 부족",
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
        "한 영수증을 나누어 촬영한 이미지를 전송 순서대로 최대 5장까지 함께 분석한다. "
        "대표 결제 항목, 브랜드, 구매처, 구매일, 금액, AS 기간, "
        "시리얼 넘버, 대분류/소분류 카테고리 후보를 추출한다. "
        "영수증 원본 파일 보관 및 연결은 receipts 저장 API의 receipt_file_ids에서 처리한다."
    ),
    response_model=CommonResponse[ReceiptOcrResultResponse],
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "examples": {
                        "receipt_image": {
                            "summary": "영수증 이미지 최대 5장 분석",
                            "value": {"file": ["receipt-1.png", "receipt-2.png"]},
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
            "description": "업로드 검증 또는 영수증 이미지 인식 실패",
            "content": {
                "application/json": {
                    "examples": {
                        "unreadable_images": {
                            "summary": "인식 실패 이미지 식별",
                            "value": _UNREADABLE_RECEIPT_EXAMPLE,
                        },
                        "invalid_upload": {
                            "summary": "업로드 파일 개수 검증 실패",
                            "value": _INVALID_UPLOAD_EXAMPLE,
                        },
                    }
                }
            },
        },
        status.HTTP_409_CONFLICT: {
            "description": "OCR 분석에 사용할 크레딧 부족",
            "content": {"application/json": {"example": _INSUFFICIENT_CREDIT_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "외부 OCR 서비스 일시 사용 불가",
            "content": {"application/json": {"example": _PROVIDER_UNAVAILABLE_EXAMPLE}},
        },
    },
)
async def extract_receipt_ocr(
    principal: CurrentPrincipalDep,
    files: Annotated[
        list[UploadFile],
        File(
            alias="file",
            description=(
                "분석할 영수증 이미지 파일. 이 API에서는 파일을 저장하지 않으며 "
                "전송 순서대로 최소 1개, 최대 5개까지 허용한다."
            ),
        ),
    ],
    use_case: ExtractReceiptOcrCommandUseCaseDep,
) -> CommonResponse[ReceiptOcrResultResponse]:
    try:
        validated_uploads = await read_and_validate_uploads(
            files=files,
            policy=RECEIPT_OCR_UPLOAD_POLICY,
        )
    except ValidationError as exception:
        logger.warning(
            "ocr_upload_validation_failed user_id=%s image_count=%d "
            "content_types=%s sizes=%s exception_type=%s",
            principal.user_id,
            len(files),
            tuple(file.content_type or "unknown" for file in files),
            tuple(file.size for file in files),
            type(exception).__name__,
        )
        raise

    result = await use_case.execute(
        ExtractReceiptOcrCommand(
            user_id=principal.user_id,
            images=tuple(
                ReceiptOcrImage(
                    file_index=file_index,
                    content=validated_upload.content,
                    content_type=validated_upload.content_type,
                )
                for file_index, validated_upload in enumerate(validated_uploads)
            ),
        )
    )

    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=ReceiptOcrResultResponse(
            item_name=result.item_name.value,
            brand_name=result.brand_name.value if result.brand_name is not None else None,
            serial_number=result.serial_number,
            payment_location=(
                result.payment_location.value if result.payment_location is not None else None
            ),
            payment_date=result.payment_date.value,
            total_amount=result.total_amount.value if result.total_amount is not None else None,
            period_months=result.period_months.value,
            expires_on=result.expires_on,
            category=result.category,
            sub_category=result.sub_category,
            needs_review=bool(result.warnings),
            warnings=list(result.warnings),
        ),
    )
