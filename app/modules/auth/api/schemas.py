from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class LoginRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "idToken": "firebase-id-token",
                }
            ]
        },
    )

    id_token: str = Field(
        alias="idToken",
        min_length=1,
        description="Firebase 로그인 후 앱이 받은 ID 토큰.",
    )


class RefreshTokenRequest(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"examples": [{"refreshToken": "refresh_7b4f3a0e_sample"}]},
    )

    refresh_token: str = Field(
        alias="refreshToken",
        description="로그인 또는 직전 토큰 재발급에서 받은 refreshToken.",
    )


class AuthTokenResponse(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sample",
                    "refreshToken": "refresh_7b4f3a0e_sample",
                    "tokenType": "Bearer",
                    "expiresIn": 1800,
                }
            ]
        },
    )

    access_token: str = Field(
        alias="accessToken",
        description="보호 API 호출에 사용하는 토큰.",
    )
    refresh_token: str = Field(
        alias="refreshToken",
        description="다음 토큰 재발급 또는 로그아웃에 사용하는 토큰.",
    )
    token_type: str = Field(
        alias="tokenType",
        description="Authorization 헤더에 사용할 토큰 타입.",
        examples=["Bearer"],
    )
    expires_in: int = Field(
        alias="expiresIn",
        description="access token 만료까지 남은 시간(초).",
        examples=[1800],
    )
