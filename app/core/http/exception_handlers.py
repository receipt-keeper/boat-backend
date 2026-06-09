from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.http.exceptions import AppError
from app.core.http.responses import ApiErrorData, CommonResponse, FieldError


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc

    response = CommonResponse(
        success=False,
        status=exc.status_code,
        data=ApiErrorData(
            message=exc.message,
            path=request.url.path,
            errors=[FieldError(field=error.field, message=error.message) for error in exc.errors],
        ),
    )
    return JSONResponse(status_code=exc.status_code, content=response.model_dump())


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc

    response = CommonResponse(
        success=False,
        status=status.HTTP_400_BAD_REQUEST,
        data=ApiErrorData(
            message="잘못된 요청입니다.",
            path=request.url.path,
            errors=[
                FieldError(
                    field=_field_name(error.get("loc", ())),
                    message=_error_message(error),
                )
                for error in exc.errors()
            ],
        ),
    )
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=response.model_dump())


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc

    response = CommonResponse(
        success=False,
        status=exc.status_code,
        data=ApiErrorData(
            message=str(exc.detail),
            path=request.url.path,
        ),
    )
    return JSONResponse(status_code=exc.status_code, content=response.model_dump())


def _field_name(location: object) -> str:
    if not isinstance(location, (list, tuple)):
        return ""

    parts = [str(part) for part in location if part not in {"body", "query", "path"}]
    return ".".join(parts)


def _error_message(error: dict[str, object]) -> str:
    context = error.get("ctx")
    if isinstance(context, dict):
        context_error = context.get("error")
        if context_error is not None:
            return str(context_error)

    return str(error.get("msg", ""))
