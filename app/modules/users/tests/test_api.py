from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.users.application.ports.user_repository import CreateUserAccountState
from app.modules.users.domain.model import User, UserEntitlement, UserSettings
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository

TEST_SETTINGS = Settings(
    jwt_secret_key="x" * 48,
    jwt_issuer="boat-backend-test",
    jwt_audience="boat-api-test",
)


@dataclass(frozen=True)
class SeededUser:
    user_id: UUID
    credentials_id: UUID
    access_token: str


async def _seed_user(
    session: AsyncSession,
    *,
    subject: str,
    email: str,
    name: str,
    free_analysis_tokens: int = 0,
    notification_enabled: bool = True,
    marketing_consent: bool = False,
) -> SeededUser:
    user = User.create(name=name, email=email)
    await SqlAlchemyUserRepository(session).create_account_state(
        state=CreateUserAccountState(
            user=user,
            settings=UserSettings.create(
                user_id=user.id,
                notification_enabled=notification_enabled,
                marketing_consent=marketing_consent,
            ),
            entitlement=UserEntitlement.create(
                user_id=user.id,
                free_analysis_tokens_remaining=free_analysis_tokens,
            ),
        )
    )
    credentials = await SqlAlchemyCredentialRepository(session).create_for_external_identity(
        identity=ExternalIdentity.create(
            issuer="google",
            subject=subject,
            provider="google",
            email=email,
            name=name,
        ),
        user_id=user.id,
        logged_in_at=datetime.now(UTC),
    )
    session_id = credentials.credentials_id
    session.add(
        auth_orm.AuthSession(
            id=session_id,
            credentials_id=credentials.credentials_id,
        )
    )
    access_token = JwtAccessTokenService.from_settings(TEST_SETTINGS).issue(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        session_id=session_id,
        role=credentials.role.value,
    )
    return SeededUser(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        access_token=access_token.token,
    )


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


def _auth_headers(seeded: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded.access_token}"}


async def test_get_me_returns_profile_envelope(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session, session.begin():
        seeded = await _seed_user(
            session,
            subject="profile-user",
            email="profile@example.com",
            name="프로필 사용자",
            free_analysis_tokens=5,
            notification_enabled=True,
            marketing_consent=False,
        )

    async with _client(postgres_session_factory) as client:
        response = await client.get("/api/v1/users/me", headers=_auth_headers(seeded))

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    data = body["data"]
    # 앱 공개 계약: PRD에 필요한 사용자 정보만 노출한다.
    assert set(data.keys()) == {
        "email",
        "name",
        "nickname",
        "profileImageUrl",
        "marketingConsent",
        "freeAnalysisTokensRemaining",
    }
    assert data["email"] == "profile@example.com"
    assert data["name"] == "프로필 사용자"
    assert data["marketingConsent"] is False
    assert data["freeAnalysisTokensRemaining"] == 5
    # 내부 식별/푸시/알림 필드는 앱 공개 응답에서 제거됐다.
    assert "normalizedEmail" not in data
    assert "notificationEnabled" not in data
    assert "pushTokenCount" not in data


async def test_patch_me_updates_marketing_consent(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session, session.begin():
        seeded = await _seed_user(
            session,
            subject="settings-user",
            email="settings@example.com",
            name="설정 사용자",
            notification_enabled=True,
            marketing_consent=False,
        )

    async with _client(postgres_session_factory) as client:
        patch_response = await client.patch(
            "/api/v1/users/me",
            headers=_auth_headers(seeded),
            json={"marketingConsent": True},
        )
        get_response = await client.get("/api/v1/users/me", headers=_auth_headers(seeded))

    patch_body = patch_response.json()
    assert patch_response.status_code == 200
    assert patch_body["success"] is True
    # 앱 공개 PATCH 응답은 marketingConsent만 노출한다.
    assert set(patch_body["data"].keys()) == {"marketingConsent"}
    assert patch_body["data"]["marketingConsent"] is True
    assert "notificationEnabled" not in patch_body["data"]

    get_body = get_response.json()
    assert get_body["data"]["marketingConsent"] is True


async def test_patch_me_rejects_unknown_fields(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session, session.begin():
        seeded = await _seed_user(
            session,
            subject="unknown-field-user",
            email="unknown@example.com",
            name="알 수 없는 필드 사용자",
            notification_enabled=True,
            marketing_consent=False,
        )

    async with _client(postgres_session_factory) as client:
        response = await client.patch(
            "/api/v1/users/me",
            headers=_auth_headers(seeded),
            json={"notificationEnabled": False},
        )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/users/me"


async def test_endpoints_require_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # 푸시 토큰 API는 앱 공개 계약에 없으므로(알림 기능 착수 전) 내 정보 조회/수정만 검증한다.
    no_token: dict[str, str] = {}
    bad_token = {"Authorization": "Bearer invalid-token"}
    requests = [
        ("GET", "/api/v1/users/me", None),
        ("PATCH", "/api/v1/users/me", {"marketingConsent": False}),
    ]

    async with _client(postgres_session_factory) as client:
        for method, path, payload in requests:
            for headers in (no_token, bad_token):
                response = await client.request(method, path, headers=headers, json=payload)
                body = response.json()
                assert response.status_code == 401, (method, path, headers)
                assert body["success"] is False, (method, path, headers)
                assert body["status"] == 401, (method, path, headers)
                assert body["data"]["path"] == path, (method, path, headers)
