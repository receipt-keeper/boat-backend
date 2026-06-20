from typing import Any

from fastapi import APIRouter, Response, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.api.schemas import AuthTokenResponse, LoginRequest, RefreshTokenRequest
from app.modules.auth.api.security import CurrentPrincipalDep
from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.result import LoginResult
from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.commands.refresh.command import RefreshTokenCommand
from app.modules.auth.application.commands.refresh.result import RefreshTokenResult
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.application.constants import AUTH_SCHEME_BEARER
from app.modules.auth.dependencies import (
    LoginCommandUseCaseDep,
    LogoutCommandUseCaseDep,
    RefreshTokenCommandUseCaseDep,
    WithdrawAccountCommandUseCaseDep,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 — 요청 형식 오류 또는 도메인 검증 실패",
    },
}

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses=_ERROR_RESPONSES,
)


def _token_response(tokens: LoginResult | RefreshTokenResult) -> AuthTokenResponse:
    return AuthTokenResponse(
        accessToken=tokens.access_token,
        refreshToken=tokens.refresh_token,
        tokenType=AUTH_SCHEME_BEARER,
        expiresIn=tokens.expires_in,
    )


@router.post(
    "/login",
    response_model=CommonResponse[AuthTokenResponse],
)
async def login(
    request: LoginRequest,
    command_use_case: LoginCommandUseCaseDep,
) -> CommonResponse[AuthTokenResponse]:
    tokens = await command_use_case.execute(LoginCommand(provider_token=request.id_token))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=_token_response(tokens),
    )


@router.post(
    "/refresh",
    response_model=CommonResponse[AuthTokenResponse],
)
async def refresh(
    request: RefreshTokenRequest,
    command_use_case: RefreshTokenCommandUseCaseDep,
) -> CommonResponse[AuthTokenResponse]:
    tokens = await command_use_case.execute(
        RefreshTokenCommand(refresh_token=request.refresh_token)
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=_token_response(tokens),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(
    request: RefreshTokenRequest,
    command_use_case: LogoutCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(LogoutCommand(refresh_token=request.refresh_token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_account(
    principal: CurrentPrincipalDep,
    command_use_case: WithdrawAccountCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(
        WithdrawAccountCommand(
            user_id=principal.user_id,
            credentials_id=principal.credentials_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
