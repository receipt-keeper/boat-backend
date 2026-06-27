from httpx import AsyncClient

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.main import app
from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.result import LoginResult
from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.commands.refresh.command import RefreshTokenCommand
from app.modules.auth.application.commands.refresh.result import RefreshTokenResult
from app.modules.auth.dependencies import (
    get_login_command_use_case,
    get_logout_command_use_case,
    get_refresh_token_command_use_case,
)
from app.modules.auth.domain.exceptions import AuthenticationError

LOGIN_SAMPLE = "firebase-sample"
REFRESH_SAMPLE = "refresh-sample"
OLD_REFRESH_SAMPLE = "old-refresh-sample"


class FakeLoginCommandUseCase:
    def __init__(self) -> None:
        self.login_id_token: str | None = None

    async def execute(self, command: LoginCommand) -> LoginResult:
        self.login_id_token = command.provider_token
        return LoginResult(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=1800,
        )


class RejectingLoginCommandUseCase(FakeLoginCommandUseCase):
    async def execute(self, command: LoginCommand) -> LoginResult:
        raise AuthenticationError()


class ConsentEnforcingLoginCommandUseCase:
    def __init__(self) -> None:
        self.command: LoginCommand | None = None

    async def execute(self, command: LoginCommand) -> LoginResult:
        self.command = command
        details: list[ErrorDetail] = []
        if not command.terms_accepted:
            details.append(
                ErrorDetail(field="termsAccepted", message="이용약관에 동의해야 합니다.")
            )
        if not command.privacy_accepted:
            details.append(
                ErrorDetail(field="privacyAccepted", message="개인정보 처리방침에 동의해야 합니다.")
            )
        if details:
            raise ValidationError(details)
        return LoginResult(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=1800,
        )


class FakeRefreshTokenCommandUseCase:
    def __init__(self) -> None:
        self.refreshed_token: str | None = None

    async def execute(self, command: RefreshTokenCommand) -> RefreshTokenResult:
        self.refreshed_token = command.refresh_token
        return RefreshTokenResult(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            expires_in=1800,
        )


class FakeLogoutCommandUseCase:
    def __init__(self) -> None:
        self.logged_out_token: str | None = None

    async def execute(self, command: LogoutCommand) -> None:
        self.logged_out_token = command.refresh_token


async def test_login_endpoint_returns_token_envelope(client: AsyncClient) -> None:
    command_use_case = FakeLoginCommandUseCase()
    app.dependency_overrides[get_login_command_use_case] = lambda: command_use_case

    response = await client.post("/api/v1/auth/login", json={"idToken": LOGIN_SAMPLE})

    assert response.status_code == 200
    assert command_use_case.login_id_token == LOGIN_SAMPLE
    assert response.json() == {
        "success": True,
        "status": 200,
        "data": {
            "accessToken": "access-token",
            "refreshToken": "refresh-token",
            "tokenType": "Bearer",
            "expiresIn": 1800,
        },
    }


async def test_login_with_consent_succeeds(client: AsyncClient) -> None:
    command_use_case = ConsentEnforcingLoginCommandUseCase()
    app.dependency_overrides[get_login_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsVersion": "v1",
            "privacyVersion": "v1",
            "termsAccepted": True,
            "privacyAccepted": True,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert command_use_case.command is not None
    assert command_use_case.command.terms_accepted is True
    assert command_use_case.command.privacy_accepted is True
    assert command_use_case.command.terms_version == "v1"
    assert body["success"] is True
    assert body["data"]["accessToken"] == "access-token"


async def test_login_missing_terms_consent_uses_422_envelope(client: AsyncClient) -> None:
    app.dependency_overrides[get_login_command_use_case] = lambda: (
        ConsentEnforcingLoginCommandUseCase()
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"idToken": LOGIN_SAMPLE, "privacyAccepted": True},
    )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/auth/login"
    assert body["data"]["errors"] == [
        {"field": "termsAccepted", "message": "이용약관에 동의해야 합니다."}
    ]


async def test_invalid_firebase_token_uses_401_envelope(client: AsyncClient) -> None:
    app.dependency_overrides[get_login_command_use_case] = lambda: RejectingLoginCommandUseCase()

    response = await client.post("/api/v1/auth/login", json={"idToken": "bad-token"})

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["status"] == 401
    assert body["data"]["message"] == "인증 정보가 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/auth/login"


async def test_malformed_login_request_uses_422_envelope(client: AsyncClient) -> None:
    app.dependency_overrides[get_login_command_use_case] = lambda: FakeLoginCommandUseCase()

    response = await client.post("/api/v1/auth/login", json={})

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["message"] == "요청 값이 올바르지 않습니다."
    assert body["data"]["path"] == "/api/v1/auth/login"
    assert body["data"]["errors"] == [{"field": "idToken", "message": "Field required"}]


async def test_login_rejects_empty_id_token_at_request_boundary(client: AsyncClient) -> None:
    command_use_case = FakeLoginCommandUseCase()
    app.dependency_overrides[get_login_command_use_case] = lambda: command_use_case

    response = await client.post("/api/v1/auth/login", json={"idToken": ""})

    body = response.json()
    assert response.status_code == 422
    assert command_use_case.login_id_token is None
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/auth/login"
    assert body["data"]["errors"] == [
        {"field": "idToken", "message": "String should have at least 1 character"}
    ]


async def test_refresh_endpoint_rotates_token(client: AsyncClient) -> None:
    command_use_case = FakeRefreshTokenCommandUseCase()
    app.dependency_overrides[get_refresh_token_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": OLD_REFRESH_SAMPLE},
    )

    assert response.status_code == 200
    assert command_use_case.refreshed_token == OLD_REFRESH_SAMPLE
    assert response.json()["data"] == {
        "accessToken": "new-access-token",
        "refreshToken": "new-refresh-token",
        "tokenType": "Bearer",
        "expiresIn": 1800,
    }


async def test_logout_endpoint_revokes_presented_refresh_token(client: AsyncClient) -> None:
    command_use_case = FakeLogoutCommandUseCase()
    app.dependency_overrides[get_logout_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refreshToken": REFRESH_SAMPLE},
    )

    assert response.status_code == 204
    assert command_use_case.logged_out_token == REFRESH_SAMPLE
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
