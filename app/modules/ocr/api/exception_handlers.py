from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError


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
