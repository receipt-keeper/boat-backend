from datetime import datetime
from typing import Final
from uuid import UUID

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient, Response

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.api.security import CurrentPrincipalDep, require_roles
from app.modules.auth.application.constants import AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.ports.credential_repository import (
    CredentialRepository,
    CredentialRepositoryProvider,
    SessionCredential,
)
from app.modules.auth.dependencies import get_current_principal_credential_repository_provider
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.infrastructure.identity_providers.firebase import (
    FirebaseExternalIdentityVerifier,
    FirebaseIdentityMapping,
)
from app.modules.auth.infrastructure.tokens.jwt import (
    JwtAccessTokenService,
)

TEST_SIGNING_KEY: Final = "x" * 48
TEST_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000001")
TEST_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000002")
TEST_SESSION_ID: Final = UUID("00000000-0000-0000-0000-000000000003")


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
    assert body["data"]["message"] == AUTHENTICATION_FAILED_MESSAGE


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
    assert identity.email_verified is True


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

    assert error.value.message == AUTHENTICATION_FAILED_MESSAGE


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

        assert error.value.message == AUTHENTICATION_FAILED_MESSAGE


def test_firebase_identity_mapping_sets_normalized_email_from_email() -> None:
    mapping = FirebaseIdentityMapping.from_settings(_test_settings())
    verifier = _firebase_verifier(mapping)

    identity = verifier._to_external_identity(
        {
            "uid": "firebase-uid",
            "email": "  User@Example.com  ",
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
    )

    assert identity.normalized_email is not None
    assert identity.normalized_email.value == "user@example.com"
    assert identity.issuer.value == "google"
    assert identity.provider.value == "google"


class CredentialStateRepository(CredentialRepository):
    def __init__(self, *, active: bool) -> None:
        self._active = active

    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        assert identity
        return None

    async def create_for_external_identity(
        self,
        *,
        identity: ExternalIdentity,
        user_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        assert identity
        assert user_id
        assert logged_in_at
        raise AssertionError("create must not be called")

    async def record_login(
        self,
        *,
        credentials_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        assert credentials_id
        assert logged_in_at
        raise AssertionError("record_login must not be called")

    async def find_credential_by_user_id(self, *, user_id: UUID) -> UserCredential | None:
        assert user_id
        raise AssertionError("find_credential_by_user_id must not be called")

    async def attach_external_identity(
        self,
        *,
        credentials_id: UUID,
        identity: ExternalIdentity,
    ) -> None:
        assert credentials_id
        assert identity
        raise AssertionError("attach_external_identity must not be called")

    async def create_session(self, *, credentials_id: UUID) -> UUID:
        assert credentials_id
        raise AssertionError("create_session must not be called")

    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        session_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        assert credentials_id
        assert session_id
        assert token_hash
        assert expires_at
        raise AssertionError("save_refresh_token must not be called")

    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> SessionCredential:
        assert token_hash
        assert new_token_hash
        assert expires_at
        raise AssertionError("rotate_refresh_token must not be called")

    async def revoke_session_by_refresh_token(self, *, token_hash: str) -> None:
        assert token_hash
        raise AssertionError("revoke_session_by_refresh_token must not be called")

    async def exists_active_credential(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> bool:
        assert user_id == TEST_USER_ID
        assert credentials_id == TEST_CREDENTIALS_ID
        return self._active

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        assert user_id == TEST_USER_ID
        assert credentials_id == TEST_CREDENTIALS_ID
        assert session_id == TEST_SESSION_ID
        return self._active

    async def delete_account_auth_state(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        assert user_id
        assert credentials_id
        raise AssertionError("delete_account_auth_state must not be called")


class StaticCredentialRepositoryProvider(CredentialRepositoryProvider):
    def __init__(self, repository: CredentialRepository) -> None:
        self._repository = repository

    def get(self) -> CredentialRepository:
        return self._repository


def _override_credential_state(test_app, *, active: bool) -> None:
    test_app.dependency_overrides[get_current_principal_credential_repository_provider] = lambda: (
        StaticCredentialRepositoryProvider(CredentialStateRepository(active=active))
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
