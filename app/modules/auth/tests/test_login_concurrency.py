from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.result import LoginResult
from app.modules.auth.application.commands.login.use_case import LoginCommandUseCase
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.application.ports.token_issuer import (
    AccessTokenIssuer,
    IssuedAccessToken,
    IssuedRefreshToken,
    RefreshTokenIssuer,
)
from app.modules.auth.dependencies import _ProvisionUserPortAdapter
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.persistence.external_identity_login_synchronizer import (
    SqlAlchemyExternalIdentityLoginSynchronizer,
)
from app.modules.users.dependencies import build_resolve_user_for_login_command_use_case
from tests.support.users_persistence import count_persisted_users


@dataclass(frozen=True)
class ConcurrentLoginContext:
    session_factory: async_sessionmaker[AsyncSession]
    identity: ExternalIdentity
    barrier: "ConcurrentLoginBarrier"


@dataclass(frozen=True)
class LoginAttempt:
    label: str
    provider_token: str
    refresh_token: str
    refresh_token_hash: str


@dataclass
class LoginOutcome:
    label: str
    result: LoginResult | None = None
    error: SQLAlchemyError | None = None


@dataclass(frozen=True)
class PersistedLoginRows:
    users: int
    credentials: int
    external_identities: int
    refresh_tokens: int


class ConcurrentLoginBarrier:
    def __init__(self, *, parties: int) -> None:
        self._parties = parties
        self._arrived = 0
        self._event = anyio.Event()
        self._lock = anyio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            self._arrived += 1
            if self._arrived == self._parties:
                self._event.set()

        with anyio.fail_after(5):
            await self._event.wait()


class BarrierExternalIdentityVerifier(ExternalIdentityVerifier):
    def __init__(self, *, identity: ExternalIdentity, barrier: ConcurrentLoginBarrier) -> None:
        self._identity = identity
        self._barrier = barrier

    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        await self._barrier.wait()
        normalized_email = (
            None
            if self._identity.normalized_email is None
            else self._identity.normalized_email.value
        )
        return ExternalIdentity.create(
            issuer=self._identity.issuer.value,
            subject=self._identity.subject.value,
            provider=self._identity.provider.value,
            email=self._identity.email,
            name=self._identity.name,
            normalized_email=normalized_email,
            email_verified=self._identity.email_verified,
        )


class DeterministicAccessTokenIssuer(AccessTokenIssuer):
    def issue(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
        role: str,
    ) -> IssuedAccessToken:
        return IssuedAccessToken(
            token=f"access:{user_id}:{credentials_id}:{session_id}:{role}",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
            expires_in=1800,
        )


class DeterministicRefreshTokenIssuer(RefreshTokenIssuer):
    def __init__(self, *, token: str, token_hash: str) -> None:
        self._token = token
        self._token_hash = token_hash

    def issue(self) -> IssuedRefreshToken:
        return IssuedRefreshToken(
            token=self._token,
            token_hash=self._token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=14),
        )


def _build_login_command_use_case(
    *,
    session: AsyncSession,
    context: ConcurrentLoginContext,
    attempt: LoginAttempt,
) -> LoginCommandUseCase:
    return LoginCommandUseCase(
        identity_verifier=BarrierExternalIdentityVerifier(
            identity=context.identity,
            barrier=context.barrier,
        ),
        login_synchronizer=SqlAlchemyExternalIdentityLoginSynchronizer(session),
        credential_repository=SqlAlchemyCredentialRepository(session),
        user_provisioner=_ProvisionUserPortAdapter(
            build_resolve_user_for_login_command_use_case(session)
        ),
        access_token_issuer=DeterministicAccessTokenIssuer(),
        refresh_token_issuer=DeterministicRefreshTokenIssuer(
            token=attempt.refresh_token,
            token_hash=attempt.refresh_token_hash,
        ),
    )


async def _run_login_attempt(
    attempt: LoginAttempt,
    context: ConcurrentLoginContext,
    outcomes: list[LoginOutcome],
) -> None:
    async with context.session_factory() as session:
        transaction = await session.begin()
        command_use_case = _build_login_command_use_case(
            session=session,
            context=context,
            attempt=attempt,
        )
        try:
            result = await command_use_case.execute(
                LoginCommand(
                    provider_token=attempt.provider_token,
                    terms_accepted=True,
                    privacy_accepted=True,
                )
            )
            await transaction.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            outcomes.append(LoginOutcome(label=attempt.label, error=exc))
            return

    outcomes.append(LoginOutcome(label=attempt.label, result=result))


async def _count_persisted_login_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> PersistedLoginRows:
    async with session_factory() as session:
        users_count = await count_persisted_users(session)
        credentials_count = await session.scalar(
            select(func.count()).select_from(auth_orm.UserCredential)
        )
        external_identities_count = await session.scalar(
            select(func.count()).select_from(auth_orm.ExternalIdentity)
        )
        refresh_tokens_count = await session.scalar(
            select(func.count()).select_from(auth_orm.RefreshToken)
        )

    return PersistedLoginRows(
        users=users_count,
        credentials=_require_count(credentials_count),
        external_identities=_require_count(external_identities_count),
        refresh_tokens=_require_count(refresh_tokens_count),
    )


def _require_count(value: int | None) -> int:
    if value is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return value


async def test_concurrent_first_login_for_same_external_identity_is_idempotent(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    context = ConcurrentLoginContext(
        session_factory=postgres_session_factory,
        identity=ExternalIdentity.create(
            issuer="google",
            subject="shared-firebase-uid",
            provider="google",
            email="shared-user@example.com",
            name="동시 로그인 사용자",
            normalized_email="shared-user@example.com",
            email_verified=True,
        ),
        barrier=ConcurrentLoginBarrier(parties=2),
    )
    attempts = [
        LoginAttempt(
            label="request-a",
            provider_token="provider-token-a",
            refresh_token="refresh-token-a",
            refresh_token_hash="refresh-token-hash-a",
        ),
        LoginAttempt(
            label="request-b",
            provider_token="provider-token-b",
            refresh_token="refresh-token-b",
            refresh_token_hash="refresh-token-hash-b",
        ),
    ]
    outcomes: list[LoginOutcome] = []

    async with anyio.create_task_group() as task_group:
        for attempt in attempts:
            task_group.start_soon(_run_login_attempt, attempt, context, outcomes)

    ordered_outcomes = sorted(outcomes, key=lambda outcome: outcome.label)
    assert len(ordered_outcomes) == 2
    login_errors = [outcome.error for outcome in ordered_outcomes if outcome.error is not None]
    assert login_errors == []

    results: list[LoginResult] = []
    for outcome in ordered_outcomes:
        assert outcome.result is not None
        results.append(outcome.result)

    token_pairs = {(result.access_token, result.refresh_token) for result in results}
    assert token_pairs == {
        (results[0].access_token, "refresh-token-a"),
        (results[1].access_token, "refresh-token-b"),
    }
    assert all(access_token.startswith("access:") for access_token, _ in token_pairs)

    rows = await _count_persisted_login_rows(postgres_session_factory)
    assert rows == PersistedLoginRows(
        users=1,
        credentials=1,
        external_identities=1,
        refresh_tokens=2,
    )
