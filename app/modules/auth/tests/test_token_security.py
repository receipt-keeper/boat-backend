from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

import jwt
import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError as PydanticValidationError

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.api.security import CurrentPrincipalDep
from app.modules.auth.application.constants import AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.infrastructure.tokens.jwt import (
    JWT_CLAIM_AUDIENCE,
    JWT_CLAIM_CREDENTIALS_ID,
    JWT_CLAIM_EXPIRES_AT,
    JWT_CLAIM_ID,
    JWT_CLAIM_ISSUED_AT,
    JWT_CLAIM_ISSUER,
    JWT_CLAIM_ROLE,
    JWT_CLAIM_SUBJECT,
)

TEST_SIGNING_KEY: Final = "x" * 48
OTHER_SIGNING_KEY: Final = "y" * 48
TEST_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000001")
TEST_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000002")


def _test_settings() -> Settings:
    return Settings(
        jwt_secret_key=TEST_SIGNING_KEY,
        jwt_issuer="boat-backend-test",
        jwt_audience="boat-api-test",
    )


def _base_access_token_claims(settings: Settings) -> dict[str, str | datetime]:
    issued_at = datetime.now(UTC)
    return {
        JWT_CLAIM_ISSUER: settings.jwt_issuer,
        JWT_CLAIM_AUDIENCE: settings.jwt_audience,
        JWT_CLAIM_SUBJECT: str(TEST_USER_ID),
        JWT_CLAIM_CREDENTIALS_ID: str(TEST_CREDENTIALS_ID),
        JWT_CLAIM_ROLE: "user",
        JWT_CLAIM_ISSUED_AT: issued_at,
        JWT_CLAIM_EXPIRES_AT: issued_at + timedelta(minutes=30),
        JWT_CLAIM_ID: "test-token-id",
    }


def _encode_access_token(
    settings: Settings,
    claims: dict[str, str | datetime],
    secret_key: str,
) -> str:
    return jwt.encode(claims, secret_key, algorithm=settings.jwt_algorithm)


async def _protected_response(settings: Settings, token: str) -> Response:
    test_app = create_app(settings)

    @test_app.get("/protected")
    async def protected(principal: CurrentPrincipalDep) -> dict[str, str]:
        return {"userId": str(principal.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        return await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )


def _assert_authentication_failed_envelope(response: Response) -> None:
    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["data"]["message"] == AUTHENTICATION_FAILED_MESSAGE


def test_prod_settings_reject_default_runtime_token_secrets() -> None:
    with pytest.raises(PydanticValidationError):
        Settings(app_env="prod")


def test_staging_settings_reject_default_refresh_token_pepper() -> None:
    with pytest.raises(PydanticValidationError):
        Settings(app_env="staging", jwt_secret_key=TEST_SIGNING_KEY)


def test_auth_runtime_settings_expose_provider_and_user_defaults() -> None:
    settings = Settings(jwt_secret_key=TEST_SIGNING_KEY)

    assert settings.firebase_provider_normalization_map == {
        "google.com": "google",
        "apple.com": "apple",
    }
    assert settings.firebase_email_verified_claim == "email_verified"
    assert settings.initial_free_analysis_tokens == 0
    assert settings.default_profile_image_url is None


async def test_current_principal_dependency_rejects_invalid_signature_with_401_envelope() -> None:
    settings = _test_settings()
    token = _encode_access_token(
        settings,
        _base_access_token_claims(settings),
        OTHER_SIGNING_KEY,
    )

    response = await _protected_response(settings, token)

    _assert_authentication_failed_envelope(response)


async def test_current_principal_dependency_rejects_invalid_issuer_with_401_envelope() -> None:
    settings = _test_settings()
    claims = _base_access_token_claims(settings)
    claims[JWT_CLAIM_ISSUER] = "unexpected-issuer"
    token = _encode_access_token(settings, claims, TEST_SIGNING_KEY)

    response = await _protected_response(settings, token)

    _assert_authentication_failed_envelope(response)


async def test_current_principal_dependency_rejects_invalid_audience_with_401_envelope() -> None:
    settings = _test_settings()
    claims = _base_access_token_claims(settings)
    claims[JWT_CLAIM_AUDIENCE] = "unexpected-audience"
    token = _encode_access_token(settings, claims, TEST_SIGNING_KEY)

    response = await _protected_response(settings, token)

    _assert_authentication_failed_envelope(response)


async def test_current_principal_dependency_rejects_malformed_subject_with_401_envelope() -> None:
    settings = _test_settings()
    claims = _base_access_token_claims(settings)
    claims[JWT_CLAIM_SUBJECT] = "not-a-uuid"
    token = _encode_access_token(settings, claims, TEST_SIGNING_KEY)

    response = await _protected_response(settings, token)

    _assert_authentication_failed_envelope(response)


async def test_current_principal_rejects_malformed_credentials_id_with_401_envelope() -> None:
    settings = _test_settings()
    claims = _base_access_token_claims(settings)
    claims[JWT_CLAIM_CREDENTIALS_ID] = "not-a-uuid"
    token = _encode_access_token(settings, claims, TEST_SIGNING_KEY)

    response = await _protected_response(settings, token)

    _assert_authentication_failed_envelope(response)


async def test_current_principal_rejects_missing_required_claims_with_401_envelope() -> None:
    settings = _test_settings()
    claims = _base_access_token_claims(settings)
    del claims[JWT_CLAIM_ROLE]
    token = _encode_access_token(settings, claims, TEST_SIGNING_KEY)

    response = await _protected_response(settings, token)

    _assert_authentication_failed_envelope(response)
