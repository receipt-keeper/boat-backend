from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class LoginRequest(AppBaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id_token: str = Field(alias="idToken")


class RefreshTokenRequest(AppBaseModel):
    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(alias="refreshToken")


class AuthTokenResponse(AppBaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    token_type: str = Field(alias="tokenType")
    expires_in: int = Field(alias="expiresIn")
