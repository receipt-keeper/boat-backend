from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.domain.exceptions import AuthenticationError, AuthorizationError


def _failure_response(*, status_code: int, message: str, path: str) -> JSONResponse:
    response = CommonResponse(
        success=False,
        status=status_code,
        data=ApiErrorData(message=message, path=path, errors=[]),
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


async def handle_authentication_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, AuthenticationError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        message=exception.message,
        path=request.url.path,
    )


async def handle_authorization_error(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, AuthorizationError):
        raise exception

    return _failure_response(
        status_code=status.HTTP_403_FORBIDDEN,
        message=exception.message,
        path=request.url.path,
    )
