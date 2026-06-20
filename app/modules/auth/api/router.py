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

# auth BC의 인증 API. 외부 신원 검증(Firebase) 뒤 백엔드 발급 토큰을 다루며,
# 도메인 예외는 전역 핸들러가 401/403/422 봉투로 변환한다.
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
    """소셜 로그인. Google/Apple만 허용한다.

    신규 가입 시 약관·개인정보 동의가 없으면 422로 거부하고, 검증된 동일 이메일의 다른
    제공자는 기존 계정에 연결한다. 성공 시 access/refresh 토큰 쌍을 발급한다.
    """
    tokens = await command_use_case.execute(
        LoginCommand(
            provider_token=request.id_token,
            terms_version=request.terms_version,
            privacy_version=request.privacy_version,
            terms_accepted=request.terms_accepted,
            privacy_accepted=request.privacy_accepted,
            marketing_consent=request.marketing_consent,
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
)
async def refresh(
    request: RefreshTokenRequest,
    command_use_case: RefreshTokenCommandUseCaseDep,
) -> CommonResponse[AuthTokenResponse]:
    """access token 재발급. refresh token을 1회용으로 회전(rotate)해 새 토큰 쌍을 발급한다.

    이미 사용된(회전된) refresh token의 재사용은 401로 거부한다.
    """
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
    """로그아웃. 제시된 refresh token의 세션을 revoke한다.

    같은 세션의 access token은 즉시 무효화되며, 성공 시 204 No Content(빈 본문)를 반환한다.
    """
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
    """회원 탈퇴.

    인증 측(credential/session/refresh/external identity)과 users 측(설정/엔타이틀먼트/
    푸시 토큰/user row)을 한 트랜잭션에서 삭제한다. 성공 시 204, 실패 시 전체 롤백한다.
    """
    await command_use_case.execute(
        WithdrawAccountCommand(
            user_id=principal.user_id,
            credentials_id=principal.credentials_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
