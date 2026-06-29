from httpx import AsyncClient

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.main import app
from app.modules.auth.application.commands.signup.command import SignupCommand
from app.modules.auth.application.commands.signup.result import SignupResult
from app.modules.auth.dependencies import get_signup_command_use_case
from app.modules.auth.domain.exceptions import UserAlreadyExistsError

LOGIN_SAMPLE = "firebase-sample"


class FakeSignupCommandUseCase:
    def __init__(self) -> None:
        self.command: SignupCommand | None = None

    async def execute(self, command: SignupCommand) -> SignupResult:
        self.command = command
        return SignupResult(
            access_token="signup-access-token",
            refresh_token="signup-refresh-token",
            expires_in=1800,
        )


class ExistingUserSignupCommandUseCase(FakeSignupCommandUseCase):
    async def execute(self, command: SignupCommand) -> SignupResult:
        self.command = command
        raise UserAlreadyExistsError()


class InvalidConsentSignupCommandUseCase(FakeSignupCommandUseCase):
    async def execute(self, command: SignupCommand) -> SignupResult:
        self.command = command
        raise ValidationError(
            [
                ErrorDetail(
                    field="termsAccepted",
                    message="이용약관에 동의해야 가입할 수 있습니다.",
                ),
                ErrorDetail(
                    field="privacyVersion",
                    message="동의한 개인정보 처리방침 버전이 필요합니다.",
                ),
            ]
        )


async def test_signup_endpoint_returns_created_token_envelope_for_new_user(
    client: AsyncClient,
) -> None:
    command_use_case = FakeSignupCommandUseCase()
    app.dependency_overrides[get_signup_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsAccepted": True,
            "privacyAccepted": True,
            "termsVersion": "2026-06-01",
            "privacyVersion": "2026-06-01",
            "marketingConsent": True,
        },
    )

    assert response.status_code == 201
    assert command_use_case.command == SignupCommand(
        provider_token=LOGIN_SAMPLE,
        terms_accepted=True,
        privacy_accepted=True,
        terms_version="2026-06-01",
        privacy_version="2026-06-01",
        marketing_consent=True,
    )
    assert response.json() == {
        "success": True,
        "status": 201,
        "data": {
            "accessToken": "signup-access-token",
            "refreshToken": "signup-refresh-token",
            "tokenType": "Bearer",
            "expiresIn": 1800,
        },
    }


async def test_signup_request_defaults_marketing_consent_to_false(
    client: AsyncClient,
) -> None:
    command_use_case = FakeSignupCommandUseCase()
    app.dependency_overrides[get_signup_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsAccepted": True,
            "privacyAccepted": True,
            "termsVersion": "2026-06-01",
            "privacyVersion": "2026-06-01",
        },
    )

    assert response.status_code == 201
    assert command_use_case.command is not None
    assert command_use_case.command.marketing_consent is False


async def test_signup_malformed_request_reports_missing_required_fields(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_signup_command_use_case] = lambda: FakeSignupCommandUseCase()

    response = await client.post(
        "/api/v1/auth/signup",
        json={},
    )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/auth/signup"
    assert body["data"]["errors"] == [
        {"field": "idToken", "message": "Field required"},
        {"field": "termsAccepted", "message": "Field required"},
        {"field": "privacyAccepted", "message": "Field required"},
        {"field": "termsVersion", "message": "Field required"},
        {"field": "privacyVersion", "message": "Field required"},
    ]


async def test_signup_request_rejects_blank_consent_versions_before_use_case(
    client: AsyncClient,
) -> None:
    command_use_case = FakeSignupCommandUseCase()
    app.dependency_overrides[get_signup_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsAccepted": True,
            "privacyAccepted": True,
            "termsVersion": "   ",
            "privacyVersion": "",
        },
    )

    body = response.json()
    assert response.status_code == 422
    assert command_use_case.command is None
    assert body["success"] is False
    assert body["status"] == 422
    assert [error["field"] for error in body["data"]["errors"]] == [
        "termsVersion",
        "privacyVersion",
    ]


async def test_signup_request_rejects_consent_versions_longer_than_storage_limit(
    client: AsyncClient,
) -> None:
    command_use_case = FakeSignupCommandUseCase()
    app.dependency_overrides[get_signup_command_use_case] = lambda: command_use_case

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsAccepted": True,
            "privacyAccepted": True,
            "termsVersion": "v" * 51,
            "privacyVersion": "v" * 51,
        },
    )

    body = response.json()
    assert response.status_code == 422
    assert command_use_case.command is None
    assert body["success"] is False
    assert body["status"] == 422
    assert [error["field"] for error in body["data"]["errors"]] == [
        "termsVersion",
        "privacyVersion",
    ]


async def test_signup_provisioning_validation_returns_field_errors(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_signup_command_use_case] = lambda: (
        InvalidConsentSignupCommandUseCase()
    )

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsAccepted": False,
            "privacyAccepted": True,
            "termsVersion": "2026-06-01",
            "privacyVersion": None,
        },
    )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/auth/signup"
    assert body["data"]["errors"] == [
        {
            "field": "termsAccepted",
            "message": "이용약관에 동의해야 가입할 수 있습니다.",
        },
        {
            "field": "privacyVersion",
            "message": "동의한 개인정보 처리방침 버전이 필요합니다.",
        },
    ]


async def test_signup_existing_user_uses_409_machine_readable_error(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_signup_command_use_case] = lambda: (
        ExistingUserSignupCommandUseCase()
    )

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "idToken": LOGIN_SAMPLE,
            "termsAccepted": True,
            "privacyAccepted": True,
            "termsVersion": "2026-06-01",
            "privacyVersion": "2026-06-01",
        },
    )

    body = response.json()
    assert response.status_code == 409
    assert body["success"] is False
    assert body["status"] == 409
    assert body["data"]["path"] == "/api/v1/auth/signup"
    assert body["data"]["code"] == "USER_ALREADY_EXISTS"


async def test_signup_openapi_documents_request_schema_and_conflict(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/openapi.json")).json()

    signup = schema["paths"]["/api/v1/auth/signup"]["post"]
    responses = signup["responses"]
    schema_ref = signup["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema_name = schema_ref.rsplit("/", maxsplit=1)[-1]
    signup_schema = schema["components"]["schemas"][schema_name]

    assert "409" in responses
    assert "USER_ALREADY_EXISTS" in responses["409"]["description"]
    assert signup_schema["properties"].keys() == {
        "idToken",
        "termsAccepted",
        "privacyAccepted",
        "termsVersion",
        "privacyVersion",
        "marketingConsent",
    }
    assert set(signup_schema["required"]) == {
        "idToken",
        "termsAccepted",
        "privacyAccepted",
        "termsVersion",
        "privacyVersion",
    }
