from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nprofile-image"


@dataclass(frozen=True, slots=True)
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
    settings: Settings = TEST_SETTINGS,
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(settings)
    test_app.state.session_factory = session_factory
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


def _auth_headers(seeded: SeededUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded.access_token}"}


def _settings(storage_root: Path) -> Settings:
    return Settings(
        jwt_secret_key=TEST_SETTINGS.jwt_secret_key,
        jwt_issuer=TEST_SETTINGS.jwt_issuer,
        jwt_audience=TEST_SETTINGS.jwt_audience,
        file_storage_root=str(storage_root),
    )


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
    assert set(data.keys()) == {
        "email",
        "name",
        "nickname",
        "profileImageUrl",
        "notificationEnabled",
        "marketingConsent",
        "freeAnalysisTokensRemaining",
    }
    assert data["email"] == "profile@example.com"
    assert data["name"] == "프로필 사용자"
    assert data["notificationEnabled"] is True
    assert data["marketingConsent"] is False
    assert data["freeAnalysisTokensRemaining"] == 5
    assert "normalizedEmail" not in data
    assert "pushTokenCount" not in data


async def test_patch_me_updates_notification_and_marketing_settings(
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
            json={"notificationEnabled": False, "marketingConsent": True},
        )
        get_response = await client.get("/api/v1/users/me", headers=_auth_headers(seeded))

    patch_body = patch_response.json()
    assert patch_response.status_code == 200
    assert patch_body["success"] is True
    assert set(patch_body["data"].keys()) == {"notificationEnabled", "marketingConsent"}
    assert patch_body["data"]["notificationEnabled"] is False
    assert patch_body["data"]["marketingConsent"] is True

    get_body = get_response.json()
    assert get_body["data"]["notificationEnabled"] is False
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
            json={"unknownField": False},
        )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/users/me"


async def test_put_profile_image_uses_uploaded_file_content_path(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "files")
    async with postgres_session_factory() as session, session.begin():
        seeded = await _seed_user(
            session,
            subject="profile-image-owner",
            email="profile-image@example.com",
            name="프로필 이미지 사용자",
        )

    async with _client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=_auth_headers(seeded),
            files={"file": ("profile.png", IMAGE_BYTES, "image/png")},
        )
        file_id = upload_response.json()["data"]["fileId"]

        put_response = await client.put(
            "/api/v1/users/me/profile-image",
            headers=_auth_headers(seeded),
            json={"fileId": file_id},
        )
        get_response = await client.get("/api/v1/users/me", headers=_auth_headers(seeded))
        content_response = await client.get(
            f"/api/v1/files/{file_id}/content",
            headers=_auth_headers(seeded),
        )
        delete_response = await client.delete(
            "/api/v1/users/me/profile-image",
            headers=_auth_headers(seeded),
        )
        cleared_response = await client.get("/api/v1/users/me", headers=_auth_headers(seeded))

    put_body = put_response.json()
    expected_profile_image_url = f"/api/v1/files/{file_id}/content"
    assert put_response.status_code == 200
    assert put_body["success"] is True
    assert put_body["data"]["profileImageUrl"] == expected_profile_image_url

    profile_data = get_response.json()["data"]
    assert set(profile_data.keys()) == {
        "email",
        "name",
        "nickname",
        "profileImageUrl",
        "notificationEnabled",
        "marketingConsent",
        "freeAnalysisTokensRemaining",
    }
    assert "profileImageFileId" not in profile_data
    assert profile_data["profileImageUrl"] == expected_profile_image_url
    assert content_response.status_code == 200
    assert content_response.headers["content-type"] == "image/png"
    assert content_response.content == IMAGE_BYTES

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert cleared_response.json()["data"]["profileImageUrl"] is None


async def test_put_profile_image_rejects_other_users_file(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "files")
    async with postgres_session_factory() as session, session.begin():
        owner = await _seed_user(
            session,
            subject="profile-image-owner-private",
            email="owner-private@example.com",
            name="파일 소유자",
        )
        other = await _seed_user(
            session,
            subject="profile-image-other-private",
            email="other-private@example.com",
            name="다른 사용자",
        )

    async with _client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=_auth_headers(other),
            files={"file": ("profile.png", IMAGE_BYTES, "image/png")},
        )
        other_file_id = upload_response.json()["data"]["fileId"]
        put_response = await client.put(
            "/api/v1/users/me/profile-image",
            headers=_auth_headers(owner),
            json={"fileId": other_file_id},
        )
        get_response = await client.get("/api/v1/users/me", headers=_auth_headers(owner))

    body = put_response.json()
    assert put_response.status_code == 404
    assert body["success"] is False
    assert get_response.json()["data"]["profileImageUrl"] is None


async def test_endpoints_require_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # 푸시 토큰 API는 앱 공개 계약에 없으므로(알림 기능 착수 전) 내 정보 조회/수정만 검증한다.
    no_token: dict[str, str] = {}
    bad_token = {"Authorization": "Bearer invalid-token"}
    requests = [
        ("GET", "/api/v1/users/me", None),
        ("PATCH", "/api/v1/users/me", {"notificationEnabled": False}),
        ("PUT", "/api/v1/users/me/profile-image", {"fileId": str(UUID(int=1))}),
        ("DELETE", "/api/v1/users/me/profile-image", None),
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
