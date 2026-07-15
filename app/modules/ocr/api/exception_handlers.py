from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.ocr.api.schemas import ReceiptOcrErrorData, ReceiptOcrFieldError
from app.modules.ocr.domain.exceptions import (
    ReceiptImageUnreadableError,
    ReceiptOcrProviderUnavailableError,
    UnsupportedReceiptError,
)

_UNSUPPORTED_RECEIPT_CODE = "UNSUPPORTED_RECEIPT"
_UNSUPPORTED_RECEIPT_FIELD_MESSAGE = "지원하지 않는 영수증입니다."
_UNREADABLE_RECEIPT_FIELD_MESSAGE = (
    "영수증 이미지를 인식하지 못했습니다. 다시 촬영하거나 수동 입력해 주세요."
)


def _failure_response(*, status_code: int, message: str, path: str) -> JSONResponse:
    response = CommonResponse(
        success=False,
        status=status_code,
        data=ApiErrorData(message=message, path=path, errors=[]),
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


async def handle_receipt_ocr_provider_unavailable_error(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, ReceiptOcrProviderUnavailableError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        message=exception.message,
        path=request.url.path,
    )


async def handle_receipt_image_unreadable_error(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, ReceiptImageUnreadableError):
        raise exception

    response = CommonResponse(
        success=False,
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        data=ReceiptOcrErrorData(
            message=exception.message,
            path=request.url.path,
            errors=[
                ReceiptOcrFieldError(
                    fileIndex=file_index,
                    message=_UNREADABLE_RECEIPT_FIELD_MESSAGE,
                )
                for file_index in exception.file_indexes
            ],
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response.model_dump(by_alias=True, exclude_none=True),
    )


async def handle_unsupported_receipt_error(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, UnsupportedReceiptError):
        raise exception

    errors = [
        *(
            ReceiptOcrFieldError(
                fileIndex=file_index,
                message=_UNSUPPORTED_RECEIPT_FIELD_MESSAGE,
            )
            for file_index in exception.unsupported_file_indexes
        ),
        *(
            ReceiptOcrFieldError(
                fileIndex=file_index,
                message=_UNREADABLE_RECEIPT_FIELD_MESSAGE,
            )
            for file_index in exception.unreadable_file_indexes
        ),
    ]
    errors.sort(key=lambda error: error.file_index if error.file_index is not None else -1)

    response = CommonResponse(
        success=False,
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        data=ReceiptOcrErrorData(
            code=_UNSUPPORTED_RECEIPT_CODE,
            message=exception.message,
            path=request.url.path,
            errors=errors,
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=response.model_dump(by_alias=True, exclude_none=True),
    )
