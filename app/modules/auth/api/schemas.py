from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class LoginRequest(AppBaseModel):
    """소셜 로그인 요청. Firebase ID 토큰과 신규 가입 시 약관 동의 정보를 담는다."""

    model_config = ConfigDict(populate_by_name=True)

    id_token: str = Field(
        alias="idToken",
        description="Firebase ID 토큰. 구글/애플 로그인 후 클라이언트가 전달한다.",
    )
    terms_version: str | None = Field(
        default=None,
        alias="termsVersion",
        description="동의한 서비스 약관 버전.",
        examples=["1.0"],
    )
    privacy_version: str | None = Field(
        default=None,
        alias="privacyVersion",
        description="동의한 개인정보 처리방침 버전.",
        examples=["1.0"],
    )
    terms_accepted: bool = Field(
        default=False,
        alias="termsAccepted",
        description="서비스 약관 동의 여부. 신규 가입 시 true가 아니면 422로 거부된다.",
    )
    privacy_accepted: bool = Field(
        default=False,
        alias="privacyAccepted",
        description="개인정보 처리방침 동의 여부. 신규 가입 시 true가 아니면 422로 거부된다.",
    )
    marketing_consent: bool = Field(
        default=False,
        alias="marketingConsent",
        description="마케팅 수신 선택 동의.",
    )


class RefreshTokenRequest(AppBaseModel):
    """토큰 재발급/로그아웃 요청. 발급받은 refresh token 원문을 담는다."""

    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(
        alias="refreshToken",
        description="로그인 또는 직전 재발급에서 받은 refresh token 원문.",
    )


class AuthTokenResponse(AppBaseModel):
    """로그인/재발급 응답. 발급된 토큰 묶음."""

    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(
        alias="accessToken",
        description="백엔드 발급 access JWT. 이후 요청의 Authorization: Bearer 헤더에 사용한다.",
    )
    refresh_token: str = Field(
        alias="refreshToken",
        description="회전되는 opaque refresh token. 다음 재발급에 사용한다.",
    )
    token_type: str = Field(
        alias="tokenType",
        description="토큰 타입.",
        examples=["Bearer"],
    )
    expires_in: int = Field(
        alias="expiresIn",
        description="access token 만료까지 남은 시간(초).",
        examples=[1800],
    )
