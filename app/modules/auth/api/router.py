from typing import Any

from fastapi import APIRouter, Response, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.api.schemas import AuthTokenResponse, LoginRequest, RefreshTokenRequest
from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.result import LoginResult
from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.commands.refresh.command import RefreshTokenCommand
from app.modules.auth.application.commands.refresh.result import RefreshTokenResult
from app.modules.auth.dependencies import (
    LoginCommandUseCaseDep,
    LogoutCommandUseCaseDep,
    RefreshTokenCommandUseCaseDep,
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
        tokenType="Bearer",
        expiresIn=tokens.expires_in,
    )


@router.post(
    "/login",
    response_model=CommonResponse[AuthTokenResponse],
    summary="소셜 로그인",
    description=(
        "Firebase 로그인 후 받은 idToken으로 백엔드 accessToken과 refreshToken을 발급한다. "
        "신규 사용자는 약관 및 개인정보 처리방침 동의값을 함께 보내야 한다."
    ),
)
async def login(
    request: LoginRequest,
    command_use_case: LoginCommandUseCaseDep,
) -> CommonResponse[AuthTokenResponse]:
    tokens = await command_use_case.execute(
        LoginCommand(
            provider_token=request.id_token,
            terms_version=request.terms_version,
            privacy_version=request.privacy_version,
            terms_accepted=request.terms_accepted,
            privacy_accepted=request.privacy_accepted,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=_token_response(tokens),
    )


@router.post(
    "/refresh",
    response_model=CommonResponse[AuthTokenResponse],
    summary="토큰 재발급",
    description=(
        "refreshToken으로 새 accessToken과 refreshToken을 발급한다. "
        "이미 재발급에 사용한 refreshToken은 다시 사용할 수 없다."
    ),
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
    summary="로그아웃",
    description="전달한 refreshToken의 로그인 상태를 종료한다. 성공하면 본문 없이 204를 반환한다.",
)
async def logout(
    request: RefreshTokenRequest,
    command_use_case: LogoutCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(LogoutCommand(refresh_token=request.refresh_token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
