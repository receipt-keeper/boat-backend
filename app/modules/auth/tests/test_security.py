from typing import Final

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.config.settings import Settings
from app.core.domain.exceptions import ValidationError
from app.main import create_app
from app.modules.auth.api.security import CurrentPrincipalDep, require_roles
from app.modules.auth.dependencies import get_active_session_checker
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.identity_providers.firebase import (
    FirebaseExternalIdentityVerifier,
    FirebaseIdentityMapping,
)
from app.modules.auth.infrastructure.tokens.jwt import (
    JwtAccessTokenService,
)
from app.modules.auth.tests.current_principal_fakes import (
    TEST_CREDENTIALS_ID,
    TEST_SESSION_ID,
    TEST_USER_ID,
    CredentialStateRepository,
    StaticActiveSessionChecker,
)

TEST_SIGNING_KEY: Final = "x" * 48


def _test_settings() -> Settings:
    return Settings(
        jwt_secret_key=TEST_SIGNING_KEY,
        jwt_issuer="boat-backend-test",
        jwt_audience="boat-api-test",
    )


def _assert_authentication_failed_envelope(response: Response) -> None:
    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["data"]["message"] == "인증 정보가 올바르지 않습니다."


def _firebase_verifier(mapping: FirebaseIdentityMapping) -> FirebaseExternalIdentityVerifier:
    verifier = FirebaseExternalIdentityVerifier.__new__(FirebaseExternalIdentityVerifier)
    verifier._identity_mapping = mapping
    return verifier


def test_firebase_mapping_reads_email_verified_claim() -> None:
    mapping = FirebaseIdentityMapping.from_settings(_test_settings())

    assert mapping.email_verified_from({"email_verified": True}) is True
    assert mapping.email_verified_from({"email_verified": False}) is False
    assert mapping.email_verified_from({}) is False


def test_firebase_identity_mapping_carries_email_verified_to_external_identity() -> None:
    mapping = FirebaseIdentityMapping.from_settings(_test_settings())
    verifier = _firebase_verifier(mapping)

    identity = verifier._to_external_identity(
        {
            "uid": "firebase-uid",
            "email": "user@example.com",
            "name": "테스트 사용자",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
    )

    assert identity.provider.value == "google"
    assert identity.issuer.value == "google"
    assert identity.email is not None
    assert identity.email.value == "user@example.com"
    assert identity.email_verified is True
    assert not hasattr(identity, "normalized_email")


def test_firebase_identity_mapping_rejects_missing_provider_claim() -> None:
    mapping = FirebaseIdentityMapping.from_settings(_test_settings())
    verifier = _firebase_verifier(mapping)

    with pytest.raises(AuthenticationError) as error:
        verifier._to_external_identity(
            {
                "uid": "firebase-uid",
                "email": "user@example.com",
                "email_verified": True,
            }
        )

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_firebase_identity_mapping_rejects_provider_outside_allowlist() -> None:
    mapping = FirebaseIdentityMapping.from_settings(_test_settings())
    verifier = _firebase_verifier(mapping)

    for disallowed_provider in ("kakao.com", "facebook.com"):
        with pytest.raises(AuthenticationError) as error:
            verifier._to_external_identity(
                {
                    "uid": "firebase-uid",
                    "email": "user@example.com",
                    "email_verified": True,
                    "firebase": {"sign_in_provider": disallowed_provider},
                }
            )

        assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_external_identity_rejects_malformed_email() -> None:
    for malformed_email in (" user@example.com ", "missing-at.example.com"):
        with pytest.raises(ValidationError):
            ExternalIdentity.create(
                issuer="google",
                subject="firebase-uid",
                provider="google",
                email=malformed_email,
                name=None,
                email_verified=True,
            )


def test_firebase_identity_mapping_keeps_single_email_value_object() -> None:
    mapping = FirebaseIdentityMapping.from_settings(_test_settings())
    verifier = _firebase_verifier(mapping)

    identity = verifier._to_external_identity(
        {
            "uid": "firebase-uid",
            "email": " user@example.com ",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
    )

    assert identity.email is not None
    assert identity.email.value == "user@example.com"
    assert not hasattr(identity, "normalized_email")
    assert identity.issuer.value == "google"
    assert identity.provider.value == "google"


def _override_credential_state(test_app: FastAPI, *, active: bool) -> None:
    test_app.dependency_overrides[get_active_session_checker] = lambda: StaticActiveSessionChecker(
        CredentialStateRepository(active=active)
    )


async def test_current_principal_dependency_accepts_valid_bearer_token() -> None:
    settings = _test_settings()
    test_app = create_app(settings)
    _override_credential_state(test_app, active=True)

    @test_app.get("/protected")
    async def protected(principal: CurrentPrincipalDep) -> dict[str, str]:
        return {"userId": str(principal.user_id), "role": principal.role}

    token = JwtAccessTokenService.from_settings(settings).issue(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token.token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "userId": "00000000-0000-0000-0000-000000000001",
        "role": "user",
    }


async def test_current_principal_rejects_stale_access_token_when_credential_is_inactive() -> None:
    settings = _test_settings()
    test_app = create_app(settings)
    _override_credential_state(test_app, active=False)

    @test_app.get("/protected")
    async def protected(principal: CurrentPrincipalDep) -> dict[str, str]:
        return {"userId": str(principal.user_id)}

    token = JwtAccessTokenService.from_settings(settings).issue(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token.token}"},
        )

    _assert_authentication_failed_envelope(response)


async def test_missing_bearer_token_uses_401_envelope() -> None:
    test_app = create_app(Settings(jwt_secret_key=TEST_SIGNING_KEY))

    @test_app.get("/protected")
    async def protected(principal: CurrentPrincipalDep) -> dict[str, str]:
        return {"userId": str(principal.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/protected")

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["data"]["message"] == "인증 정보가 필요합니다."


async def test_expired_access_token_uses_401_envelope() -> None:
    settings = _test_settings().model_copy(update={"access_token_expires_minutes": -1})
    test_app = create_app(settings)

    @test_app.get("/protected")
    async def protected(principal: CurrentPrincipalDep) -> dict[str, str]:
        return {"userId": str(principal.user_id)}

    token = JwtAccessTokenService.from_settings(settings).issue(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token.token}"},
        )

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["data"]["message"] == "인증 정보가 올바르지 않습니다."


async def test_require_roles_uses_403_envelope_for_insufficient_role() -> None:
    settings = _test_settings()
    test_app = create_app(settings)
    _override_credential_state(test_app, active=True)

    @test_app.get("/admin", dependencies=[Depends(require_roles("admin"))])
    async def admin() -> dict[str, bool]:
        return {"ok": True}

    token = JwtAccessTokenService.from_settings(settings).issue(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/admin",
            headers={"Authorization": f"Bearer {token.token}"},
        )

    body = response.json()
    assert response.status_code == 403
    assert body["success"] is False
    assert body["data"]["message"] == "접근 권한이 없습니다."
