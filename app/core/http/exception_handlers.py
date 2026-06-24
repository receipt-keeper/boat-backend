import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.domain.exceptions import (
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.core.http.responses import ApiErrorData, CommonResponse, FieldError

logger = logging.getLogger(__name__)


def _failure_response(
    *,
    status_code: int,
    message: str,
    path: str,
    errors: list[FieldError] | None = None,
) -> JSONResponse:
    response = CommonResponse(
        success=False,
        status=status_code,
        data=ApiErrorData(
            message=message,
            path=path,
            errors=errors or [],
        ),
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


async def handle_domain_validation_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, ValidationError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        message=exception.message,
        path=request.url.path,
        errors=[
            FieldError(field=detail.field, message=detail.message) for detail in exception.details
        ],
    )


async def handle_not_found_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, NotFoundError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_404_NOT_FOUND,
        message=exception.message,
        path=request.url.path,
    )


async def handle_conflict_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, ConflictError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_409_CONFLICT,
        message=exception.message,
        path=request.url.path,
    )


async def handle_external_service_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, ExternalServiceError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        message=exception.message,
        path=request.url.path,
    )


async def handle_domain_error(request: Request, exception: Exception) -> JSONResponse:
    """카테고리 없는 DomainError의 안전망 — 도메인 규칙 위반은 클라이언트 책임(400)으로 본다.

    새 도메인 예외는 의미 카테고리(ValidationError, NotFoundError, ...)를 상속해야 한다.
    """
    if not isinstance(exception, DomainError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        message=exception.message,
        path=request.url.path,
    )


async def handle_request_validation_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, RequestValidationError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        message="요청 값이 올바르지 않습니다.",
        path=request.url.path,
        errors=[FieldError.from_pydantic_error(error) for error in exception.errors()],
    )


async def handle_http_exception(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, StarletteHTTPException):
        raise exception

    return _failure_response(
        status_code=exception.status_code,
        message=exception.detail if isinstance(exception.detail, str) else str(exception.detail),
        path=request.url.path,
    )


async def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
    logger.exception("처리되지 않은 예외 발생", exc_info=exception)

    return _failure_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="서버 내부 오류가 발생했습니다.",
        path=request.url.path,
    )
