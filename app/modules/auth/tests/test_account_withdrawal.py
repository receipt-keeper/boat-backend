from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.application.ports.push_cleanup import PushCleanup
from app.modules.auth.dependencies import get_push_cleanup
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from tests.support.users_persistence import (
    count_persisted_users,
    create_persisted_user,
    persisted_user_exists,
)

TEST_SETTINGS = Settings(
    jwt_secret_key="x" * 48,
    jwt_issuer="boat-backend-test",
    jwt_audience="boat-api-test",
)


@dataclass(frozen=True)
class SeededAccount:
    user_id: UUID
    credentials_id: UUID
    access_token: str


class RecordingPushCleanup(PushCleanup):
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def cleanup_withdrawn_account(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        self.calls.append((user_id, credentials_id))


class FailingPushCleanup(PushCleanup):
    async def cleanup_withdrawn_account(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        assert user_id
        assert credentials_id
        raise RuntimeError("push cleanup failed")


async def _seed_account(
    session: AsyncSession,
    *,
    subject: str,
    refresh_token_hash: str,
) -> SeededAccount:
    user = await create_persisted_user(
        session,
        name="탈퇴 테스트 사용자",
        email=f"{subject}@example.com",
    )
    credentials = await SqlAlchemyCredentialRepository(session).create_for_external_identity(
        identity=ExternalIdentity.create(
            issuer="firebase",
            subject=subject,
            provider="google.com",
            email=user.email,
            name=user.name,
        ),
        user_id=user.id,
        logged_in_at=datetime.now(UTC),
    )
    await SqlAlchemyCredentialRepository(session).save_refresh_token(
        credentials_id=credentials.credentials_id,
        token_hash=refresh_token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    access_token = JwtAccessTokenService.from_settings(TEST_SETTINGS).issue(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        role=credentials.role.value,
    )
    return SeededAccount(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        access_token=access_token.token,
    )


async def _count_rows(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with session_factory() as session:
        users_count = await count_persisted_users(session)
        credentials_count = await session.scalar(
            select(func.count()).select_from(auth_orm.UserCredential)
        )
        identities_count = await session.scalar(
            select(func.count()).select_from(auth_orm.ExternalIdentity)
        )
        refresh_tokens_count = await session.scalar(
            select(func.count()).select_from(auth_orm.RefreshToken)
        )

    return {
        "users": users_count,
        "credentials": _require_count(credentials_count),
        "external_identities": _require_count(identities_count),
        "refresh_tokens": _require_count(refresh_tokens_count),
    }


def _require_count(value: int | None) -> int:
    if value is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return value


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
    push_cleanup: PushCleanup,
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(TEST_SETTINGS)
    test_app.dependency_overrides[get_push_cleanup] = lambda: push_cleanup
    test_app.state.session_factory = session_factory

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


async def test_delete_me_requires_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(postgres_session_factory, RecordingPushCleanup()) as client:
        response = await client.delete("/api/v1/auth/me")
        invalid_response = await client.delete(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["data"]["path"] == "/api/v1/auth/me"

    invalid_body = invalid_response.json()
    assert invalid_response.status_code == 401
    assert invalid_body["success"] is False
    assert invalid_body["data"]["path"] == "/api/v1/auth/me"


async def test_delete_me_withdraws_account_and_runs_push_cleanup(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with postgres_session_factory() as session, session.begin():
        current = await _seed_account(
            session,
            subject="current-user",
            refresh_token_hash="current-refresh-hash",
        )
        other = await _seed_account(
            session,
            subject="other-user",
            refresh_token_hash="other-refresh-hash",
        )

    cleanup = RecordingPushCleanup()
    async with _client(postgres_session_factory, cleanup) as client:
        response = await client.delete(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )
        stale_response = await client.delete(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )

    assert response.status_code == 204
    assert response.content == b""
    assert stale_response.status_code == 401
    assert cleanup.calls == [(current.user_id, current.credentials_id)]

    async with postgres_session_factory() as session:
        assert not await persisted_user_exists(session, current.user_id)
        assert await session.get(auth_orm.UserCredential, current.credentials_id) is None
        assert await persisted_user_exists(session, other.user_id)
        assert await session.get(auth_orm.UserCredential, other.credentials_id) is not None
        current_identity_rows = await session.scalars(
            select(auth_orm.ExternalIdentity).where(
                auth_orm.ExternalIdentity.credentials_id == current.credentials_id
            )
        )
        current_refresh_rows = await session.scalars(
            select(auth_orm.RefreshToken).where(
                auth_orm.RefreshToken.credentials_id == current.credentials_id
            )
        )
        other_identity_rows = await session.scalars(
            select(auth_orm.ExternalIdentity).where(
                auth_orm.ExternalIdentity.credentials_id == other.credentials_id
            )
        )
        other_refresh_rows = await session.scalars(
            select(auth_orm.RefreshToken).where(
                auth_orm.RefreshToken.credentials_id == other.credentials_id
            )
        )

    assert list(current_identity_rows) == []
    assert list(current_refresh_rows) == []
    assert len(list(other_identity_rows)) == 1
    assert len(list(other_refresh_rows)) == 1
    assert await _count_rows(postgres_session_factory) == {
        "users": 1,
        "credentials": 1,
        "external_identities": 1,
        "refresh_tokens": 1,
    }

    with capsys.disabled():
        print(
            "manual_qa account_withdrawal "
            "http_unauthenticated=401 authenticated_delete=204 stale_token=401 "
            "rows_after_delete users=1 credentials=1 external_identities=1 refresh_tokens=1 "
            f"cleanup_calls={cleanup.calls}"
        )


async def test_delete_me_rolls_back_when_push_cleanup_fails(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with postgres_session_factory() as session, session.begin():
        current = await _seed_account(
            session,
            subject="rollback-user",
            refresh_token_hash="rollback-refresh-hash",
        )

    async with _client(postgres_session_factory, FailingPushCleanup()) as client:
        response = await client.delete(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["status"] == 500
    assert body["data"]["message"] == "서버 내부 오류가 발생했습니다."
    assert body["data"]["path"] == "/api/v1/auth/me"
    assert await _count_rows(postgres_session_factory) == {
        "users": 1,
        "credentials": 1,
        "external_identities": 1,
        "refresh_tokens": 1,
    }

    with capsys.disabled():
        print(
            "manual_qa account_withdrawal_cleanup_failure "
            "http_status=500 rollback_rows users=1 credentials=1 "
            "external_identities=1 refresh_tokens=1"
        )
