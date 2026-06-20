import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import Settings
from app.main import create_app
from app.modules.auth.dependencies import (
    get_withdrawal_cleanup_command_use_case,
)
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from app.modules.users.infrastructure.persistence import orm as users_orm
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
EVIDENCE_DIR = Path(".omo/evidence/auth-users-bc-prd-completion")


@dataclass(frozen=True)
class SeededAccount:
    user_id: UUID
    credentials_id: UUID
    access_token: str


async def _seed_full_account(
    session: AsyncSession,
    *,
    subject: str,
    refresh_token_hash: str,
    push_token_device_id: str | None = None,
) -> SeededAccount:
    """Seed users (user/settings/entitlement/push) + auth (credential/session/refresh)."""
    user = await create_persisted_user(
        session,
        name="탈퇴 테스트 사용자",
        email=f"{subject}@example.com",
    )
    # Seed users-side account state (settings + entitlement)
    from app.modules.users.domain.model import UserEntitlement, UserSettings

    settings = UserSettings.create(user_id=user.id)
    entitlement = UserEntitlement.create(user_id=user.id)
    session.add_all(
        [
            _settings_record(settings),
            _entitlement_record(entitlement),
        ]
    )
    # Optionally seed push token
    if push_token_device_id is not None:
        session.add(
            users_orm.UserPushToken(
                user_id=user.id,
                device_id=push_token_device_id,
                fcm_token=f"fcm-{subject}-{push_token_device_id}",
                platform="android",
            )
        )

    # Seed auth side
    credentials = await SqlAlchemyCredentialRepository(session).create_for_external_identity(
        identity=ExternalIdentity.create(
            issuer="google",
            subject=subject,
            provider="google",
            email=user.email,
            name=user.name,
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
    await SqlAlchemyCredentialRepository(session).save_refresh_token(
        credentials_id=credentials.credentials_id,
        session_id=session_id,
        token_hash=refresh_token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    access_token = JwtAccessTokenService.from_settings(TEST_SETTINGS).issue(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        session_id=session_id,
        role=credentials.role.value,
    )
    await session.flush()
    return SeededAccount(
        user_id=user.id,
        credentials_id=credentials.credentials_id,
        access_token=access_token.token,
    )


def _settings_record(settings: object) -> users_orm.UserSettings:
    from app.modules.users.domain.model import UserSettings as DomainSettings

    assert isinstance(settings, DomainSettings)
    # UserSettings.id == user_id (entity PK is the user_id)
    return users_orm.UserSettings(
        user_id=settings.id,
        notification_enabled=settings.notification_enabled,
        marketing_consent=settings.marketing_consent,
    )


def _entitlement_record(entitlement: object) -> users_orm.UserEntitlement:
    from app.modules.users.domain.model import UserEntitlement as DomainEntitlement

    assert isinstance(entitlement, DomainEntitlement)
    # UserEntitlement.id == user_id
    return users_orm.UserEntitlement(
        user_id=entitlement.id,
        free_analysis_tokens_remaining=entitlement.free_analysis_tokens_remaining.value,
    )


async def _count_all_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with session_factory() as session:
        users_count = await count_persisted_users(session)
        credentials_count = await session.scalar(
            select(func.count()).select_from(auth_orm.UserCredential)
        )
        identities_count = await session.scalar(
            select(func.count()).select_from(auth_orm.ExternalIdentity)
        )
        auth_sessions_count = await session.scalar(
            select(func.count()).select_from(auth_orm.AuthSession)
        )
        refresh_tokens_count = await session.scalar(
            select(func.count()).select_from(auth_orm.RefreshToken)
        )
        settings_count = await session.scalar(
            select(func.count()).select_from(users_orm.UserSettings)
        )
        entitlements_count = await session.scalar(
            select(func.count()).select_from(users_orm.UserEntitlement)
        )
        push_tokens_count = await session.scalar(
            select(func.count()).select_from(users_orm.UserPushToken)
        )

    def _req(v: int | None) -> int:
        if v is None:
            raise AssertionError("PostgreSQL COUNT returned no value")
        return v

    return {
        "users": users_count,
        "user_credentials": _req(credentials_count),
        "external_identities": _req(identities_count),
        "auth_sessions": _req(auth_sessions_count),
        "refresh_tokens": _req(refresh_tokens_count),
        "user_settings": _req(settings_count),
        "user_entitlements": _req(entitlements_count),
        "user_push_tokens": _req(push_tokens_count),
    }


@asynccontextmanager
async def _plain_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


@asynccontextmanager
async def _client_with_failing_cleanup(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Inject a failing users cleanup into the REAL withdraw use case so the REAL
    request transaction must roll back the auth delete atomically (no fake use case)."""

    class _FailingWithdrawalCleanup(WithdrawalCleanupCommandUseCase):
        def __init__(self) -> None:
            pass

        async def execute(self, command: WithdrawalCleanupCommand) -> None:
            raise RuntimeError("users cleanup failed (injected failure)")

    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory
    test_app.dependency_overrides[get_withdrawal_cleanup_command_use_case] = lambda: (
        _FailingWithdrawalCleanup()
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        yield client


def _write_evidence(name: str, payload: dict[str, object]) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_delete_me_requires_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _plain_client(postgres_session_factory) as client:
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


async def test_delete_me_withdraws_full_account(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Happy path: DELETE /api/v1/auth/me removes ALL owned rows; second account untouched."""
    async with postgres_session_factory() as session, session.begin():
        current = await _seed_full_account(
            session,
            subject="current-user",
            refresh_token_hash="current-refresh-hash",
            push_token_device_id="device-current",
        )
        other = await _seed_full_account(
            session,
            subject="other-user",
            refresh_token_hash="other-refresh-hash",
            push_token_device_id="device-other",
        )

    async with _plain_client(postgres_session_factory) as client:
        response = await client.delete(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )
        # stale token reuse must 401
        stale_response = await client.delete(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {current.access_token}"},
        )

    assert response.status_code == 204
    assert response.content == b""
    assert stale_response.status_code == 401

    async with postgres_session_factory() as session:
        # current user row gone
        assert not await persisted_user_exists(session, current.user_id)
        # auth rows for current gone
        assert await session.get(auth_orm.UserCredential, current.credentials_id) is None
        current_identities = list(
            await session.scalars(
                select(auth_orm.ExternalIdentity).where(
                    auth_orm.ExternalIdentity.credentials_id == current.credentials_id
                )
            )
        )
        current_refresh_tokens = list(
            await session.scalars(
                select(auth_orm.RefreshToken).where(
                    auth_orm.RefreshToken.credentials_id == current.credentials_id
                )
            )
        )
        current_push_tokens = list(
            await session.scalars(
                select(users_orm.UserPushToken).where(
                    users_orm.UserPushToken.user_id == current.user_id
                )
            )
        )
        current_settings = await session.get(users_orm.UserSettings, current.user_id)
        current_entitlements = await session.get(users_orm.UserEntitlement, current.user_id)

        assert current_identities == []
        assert current_refresh_tokens == []
        assert current_push_tokens == []
        assert current_settings is None
        assert current_entitlements is None

        # other account fully intact
        assert await persisted_user_exists(session, other.user_id)
        assert await session.get(auth_orm.UserCredential, other.credentials_id) is not None
        other_identities = list(
            await session.scalars(
                select(auth_orm.ExternalIdentity).where(
                    auth_orm.ExternalIdentity.credentials_id == other.credentials_id
                )
            )
        )
        assert len(other_identities) == 1
        other_push_tokens = list(
            await session.scalars(
                select(users_orm.UserPushToken).where(
                    users_orm.UserPushToken.user_id == other.user_id
                )
            )
        )
        assert len(other_push_tokens) == 1

    counts = await _count_all_rows(postgres_session_factory)
    assert counts == {
        "users": 1,
        "user_credentials": 1,
        "external_identities": 1,
        "auth_sessions": 1,
        "refresh_tokens": 1,
        "user_settings": 1,
        "user_entitlements": 1,
        "user_push_tokens": 1,
    }

    evidence = {
        "scenario": "account_withdrawal",
        "http_status_delete": response.status_code,
        "http_status_stale": stale_response.status_code,
        **{f"remaining_{k}": v for k, v in counts.items()},
    }
    path = _write_evidence("task-10-withdraw-green.log", evidence)
    assert path.is_file()


async def test_delete_me_rolls_back_when_users_cleanup_fails(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Rollback path: failing users cleanup -> 500; ALL rows (auth + users + push tokens) intact."""
    async with postgres_session_factory() as session, session.begin():
        current = await _seed_full_account(
            session,
            subject="rollback-user",
            refresh_token_hash="rollback-refresh-hash",
            push_token_device_id="device-rollback",
        )

    async with _client_with_failing_cleanup(postgres_session_factory) as client:
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

    counts = await _count_all_rows(postgres_session_factory)
    assert counts == {
        "users": 1,
        "user_credentials": 1,
        "external_identities": 1,
        "auth_sessions": 1,
        "refresh_tokens": 1,
        "user_settings": 1,
        "user_entitlements": 1,
        "user_push_tokens": 1,
    }, f"Expected all rows intact after rollback but got: {counts}"

    evidence = {
        "scenario": "account_withdrawal_cleanup_failure",
        "http_status": response.status_code,
        **{f"rollback_{k}": v for k, v in counts.items()},
    }
    path = _write_evidence("task-10-withdraw-rollback.log", evidence)
    assert path.is_file()
