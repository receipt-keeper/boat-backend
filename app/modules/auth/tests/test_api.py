from httpx import AsyncClient

from app.main import app
from app.modules.auth.application.constants import AUTH_SCHEME_BEARER, AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.login.schemas import LoginCommand, LoginResult
from app.modules.auth.application.logout.schemas import LogoutCommand
from app.modules.auth.application.refresh.schemas import RefreshTokenCommand, RefreshTokenResult
from app.modules.auth.dependencies import (
    get_login_use_case,
    get_logout_use_case,
    get_refresh_token_use_case,
)
from app.modules.auth.domain.exceptions import AuthenticationError

LOGIN_SAMPLE = "firebase-sample"
REFRESH_SAMPLE = "refresh-sample"
OLD_REFRESH_SAMPLE = "old-refresh-sample"


class FakeLoginUseCase:
    def __init__(self) -> None:
        self.login_id_token: str | None = None

    async def execute(self, command: LoginCommand) -> LoginResult:
        self.login_id_token = command.provider_token
        return LoginResult(
            access_token="access-token",
            refresh_token="refresh-token",
            token_type=AUTH_SCHEME_BEARER,
            expires_in=1800,
        )


class RejectingLoginUseCase(FakeLoginUseCase):
    async def execute(self, command: LoginCommand) -> LoginResult:
        raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)


class FakeRefreshTokenUseCase:
    def __init__(self) -> None:
        self.refreshed_token: str | None = None

    async def execute(self, command: RefreshTokenCommand) -> RefreshTokenResult:
        self.refreshed_token = command.refresh_token
        return RefreshTokenResult(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            token_type=AUTH_SCHEME_BEARER,
            expires_in=1800,
        )


class FakeLogoutUseCase:
    def __init__(self) -> None:
        self.logged_out_token: str | None = None

    async def execute(self, command: LogoutCommand) -> None:
        self.logged_out_token = command.refresh_token


async def test_login_endpoint_returns_token_envelope(client: AsyncClient) -> None:
    use_case = FakeLoginUseCase()
    app.dependency_overrides[get_login_use_case] = lambda: use_case

    response = await client.post("/api/v1/auth/login", json={"idToken": LOGIN_SAMPLE})

    assert response.status_code == 200
    assert use_case.login_id_token == LOGIN_SAMPLE
    assert response.json() == {
        "success": True,
        "status": 200,
        "data": {
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "tokenType": AUTH_SCHEME_BEARER,
            "expiresIn": 1800,
        },
    }


async def test_invalid_firebase_token_uses_401_envelope(client: AsyncClient) -> None:
    app.dependency_overrides[get_login_use_case] = lambda: RejectingLoginUseCase()

    response = await client.post("/api/v1/auth/login", json={"idToken": "bad-token"})

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["status"] == 401
    assert body["data"]["message"] == AUTHENTICATION_FAILED_MESSAGE
    assert body["data"]["path"] == "/api/v1/auth/login"


async def test_malformed_login_request_uses_422_envelope(client: AsyncClient) -> None:
    app.dependency_overrides[get_login_use_case] = lambda: FakeLoginUseCase()

    response = await client.post("/api/v1/auth/login", json={})

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/auth/login"
    assert body["data"]["errors"] == [{"field": "idToken", "message": "Field required"}]


async def test_refresh_endpoint_rotates_token(client: AsyncClient) -> None:
    use_case = FakeRefreshTokenUseCase()
    app.dependency_overrides[get_refresh_token_use_case] = lambda: use_case

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": OLD_REFRESH_SAMPLE},
    )

    assert response.status_code == 200
    assert use_case.refreshed_token == OLD_REFRESH_SAMPLE
    assert response.json()["data"] == {
        "accessToken": "new-access-token",
        "refreshToken": "new-refresh-token",
        "tokenType": AUTH_SCHEME_BEARER,
        "expiresIn": 1800,
    }


async def test_logout_endpoint_revokes_presented_refresh_token(client: AsyncClient) -> None:
    use_case = FakeLogoutUseCase()
    app.dependency_overrides[get_logout_use_case] = lambda: use_case

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refreshToken": REFRESH_SAMPLE},
    )

    assert response.status_code == 204
    assert use_case.logged_out_token == REFRESH_SAMPLE
    assert response.content == b""


async def test_auth_openapi_documents_error_envelopes(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    login_responses = schema["paths"]["/api/v1/auth/login"]["post"]["responses"]
    refresh_responses = schema["paths"]["/api/v1/auth/refresh"]["post"]["responses"]
    logout_responses = schema["paths"]["/api/v1/auth/logout"]["post"]["responses"]

    assert "401" in login_responses
    assert "422" in login_responses
    assert "401" in refresh_responses
    assert "422" in refresh_responses
    assert "204" in logout_responses
    assert "401" in logout_responses
    assert "422" in logout_responses
    assert login_responses["401"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "CommonResponse_ApiErrorData_"
    )
