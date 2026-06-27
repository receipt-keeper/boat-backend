from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.unit_of_work import DeferredCommitUnitOfWork
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
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


@dataclass(frozen=True, slots=True)
class ConcurrentLoginContext:
    session_factory: async_sessionmaker[AsyncSession]
    identities: dict[str, ExternalIdentity]
    barrier: "ConcurrentLoginBarrier"


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    label: str
    provider_token: str
    refresh_token: str
    refresh_token_hash: str


@dataclass(slots=True)
class LoginOutcome:
    label: str
    result: LoginResult | None = None
    error: SQLAlchemyError | None = None


@dataclass(frozen=True, slots=True)
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
    def __init__(self, *, context: ConcurrentLoginContext) -> None:
        self._context = context

    async def verify(self, provider_token: str) -> ExternalIdentity:
        assert provider_token
        await self._context.barrier.wait()
        identity = self._context.identities[provider_token]
        return ExternalIdentity.create(
            issuer=identity.issuer.value,
            subject=identity.subject.value,
            provider=identity.provider.value,
            email=None if identity.email is None else identity.email.value,
            name=identity.name,
            email_verified=identity.email_verified,
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


async def run_login_attempt(
    attempt: LoginAttempt,
    context: ConcurrentLoginContext,
    outcomes: list[LoginOutcome],
) -> None:
    async with context.session_factory() as session:
        command_use_case = _build_login_command_use_case(
            session=session,
            context=context,
            attempt=attempt,
        )
        try:
            result = await command_use_case.execute(
                LoginCommand(
                    provider_token=attempt.provider_token,
                    terms_version="1.0",
                    privacy_version="1.0",
                    terms_accepted=True,
                    privacy_accepted=True,
                )
            )
        except SQLAlchemyError as exc:
            await session.rollback()
            outcomes.append(LoginOutcome(label=attempt.label, error=exc))
            return

    outcomes.append(LoginOutcome(label=attempt.label, result=result))


async def count_persisted_login_rows(
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


def _build_login_command_use_case(
    *,
    session: AsyncSession,
    context: ConcurrentLoginContext,
    attempt: LoginAttempt,
) -> LoginCommandUseCase:
    return LoginCommandUseCase(
        identity_verifier=BarrierExternalIdentityVerifier(
            context=context,
        ),
        login_synchronizer=SqlAlchemyExternalIdentityLoginSynchronizer(session),
        credential_repository=SqlAlchemyCredentialRepository(session),
        user_provisioner=_ProvisionUserPortAdapter(
            build_resolve_user_for_login_command_use_case(
                session,
                DeferredCommitUnitOfWork(),
            )
        ),
        access_token_issuer=DeterministicAccessTokenIssuer(),
        refresh_token_issuer=DeterministicRefreshTokenIssuer(
            token=attempt.refresh_token,
            token_hash=attempt.refresh_token_hash,
        ),
        unit_of_work=SqlAlchemyUnitOfWork(session),
    )


def _require_count(value: int | None) -> int:
    if value is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return value
