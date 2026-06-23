from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest

from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.infrastructure.tokens.jwt import (
    JWT_CLAIM_CREDENTIALS_ID,
    JWT_CLAIM_ROLE,
    JWT_CLAIM_SESSION_ID,
    JWT_CLAIM_SUBJECT,
    JwtAccessTokenService,
)
from app.modules.auth.tests.service_fakes import TEST_SIGNING_KEY


def test_access_token_contains_principal_claims() -> None:
    manager = JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
    user_id = UUID("00000000-0000-0000-0000-000000000001")
    credentials_id = UUID("00000000-0000-0000-0000-000000000002")
    session_id = UUID("00000000-0000-0000-0000-000000000003")

    issued = manager.issue(
        user_id=user_id,
        credentials_id=credentials_id,
        session_id=session_id,
        role="admin",
    )
    principal = manager.verify(issued.token)

    assert principal.user_id == user_id
    assert principal.credentials_id == credentials_id
    assert principal.session_id == session_id
    assert principal.role == "admin"
    assert issued.expires_at > datetime.now(UTC)


def test_access_token_verify_rejects_malformed_subject_with_authentication_error() -> None:
    manager = _access_token_service()
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_SUBJECT] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_malformed_credentials_id_with_authentication_error() -> None:
    manager = _access_token_service()
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_CREDENTIALS_ID] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_missing_required_claims_with_authentication_error() -> None:
    manager = _access_token_service()
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    del claims[JWT_CLAIM_ROLE]
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_malformed_session_id_with_authentication_error() -> None:
    manager = _access_token_service()
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    claims[JWT_CLAIM_SESSION_ID] = "not-a-uuid"
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def test_access_token_verify_rejects_missing_session_id_with_authentication_error() -> None:
    manager = _access_token_service()
    issued = manager.issue(
        user_id=uuid4(),
        credentials_id=uuid4(),
        session_id=uuid4(),
        role="user",
    )
    claims = jwt.decode(issued.token, options={"verify_signature": False})
    del claims[JWT_CLAIM_SESSION_ID]
    malformed_token = jwt.encode(claims, TEST_SIGNING_KEY, algorithm="HS256")

    with pytest.raises(AuthenticationError) as error:
        manager.verify(malformed_token)

    assert error.value.message == "인증 정보가 올바르지 않습니다."


def _access_token_service() -> JwtAccessTokenService:
    return JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )
