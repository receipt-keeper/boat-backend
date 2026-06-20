from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class LoginRequest(AppBaseModel):
    """POST /auth/login 요청. Firebase ID 토큰과 신규 가입 시 약관 동의 정보."""

    model_config = ConfigDict(populate_by_name=True)

    # Firebase ID 토큰(구글/애플 로그인)
    id_token: str = Field(alias="idToken")
    # 동의한 서비스 약관 버전
    terms_version: str | None = Field(default=None, alias="termsVersion")
    # 동의한 개인정보 처리방침 버전
    privacy_version: str | None = Field(default=None, alias="privacyVersion")
    # 서비스 약관 동의 여부(신규 가입 시 필수)
    terms_accepted: bool = Field(default=False, alias="termsAccepted")
    # 개인정보 처리방침 동의 여부(신규 가입 시 필수)
    privacy_accepted: bool = Field(default=False, alias="privacyAccepted")
    # 마케팅 수신 선택 동의
    marketing_consent: bool = Field(default=False, alias="marketingConsent")


class RefreshTokenRequest(AppBaseModel):
    """POST /auth/refresh 및 POST /auth/logout 요청. 발급받은 refresh token 원문."""

    model_config = ConfigDict(populate_by_name=True)

    # 클라이언트가 보관 중인 refresh token
    refresh_token: str = Field(alias="refreshToken")


class AuthTokenResponse(AppBaseModel):
    """POST /auth/login 및 POST /auth/refresh 응답. 발급된 토큰 묶음."""

    model_config = ConfigDict(populate_by_name=True)

    # 백엔드 발급 access JWT
    access_token: str = Field(alias="accessToken")
    # 회전되는 opaque refresh token
    refresh_token: str = Field(alias="refreshToken")
    # 토큰 타입(Bearer)
    token_type: str = Field(alias="tokenType")
    # access token 만료까지 남은 초
    expires_in: int = Field(alias="expiresIn")
