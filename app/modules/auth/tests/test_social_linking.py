from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.application.commands.login.command import LoginCommand
from app.modules.auth.application.commands.login.use_case import LoginCommandUseCase
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.dependencies import _ProvisionUserPortAdapter
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.auth.infrastructure.persistence.external_identity_login_synchronizer import (
    SqlAlchemyExternalIdentityLoginSynchronizer,
)
from app.modules.auth.tests.service_fakes import (
    build_access_token_issuer,
    build_refresh_token_service,
)
from app.modules.users.dependencies import build_resolve_user_for_login_command_use_case
from tests.support.users_persistence import count_persisted_users

EVIDENCE_DIR = Path(".omo/evidence/auth-users-bc-prd-completion")


@dataclass(frozen=True)
class IdentitySpec:
    subject: str
    provider: str
    email: str
    email_verified: bool = True


class ScriptedExternalIdentityVerifier(ExternalIdentityVerifier):
    def __init__(self, *, specs: dict[str, IdentitySpec]) -> None:
        self._specs = specs

    async def verify(self, provider_token: str) -> ExternalIdentity:
        spec = self._specs[provider_token]
        return ExternalIdentity.create(
            issuer=spec.provider,
            subject=spec.subject,
            provider=spec.provider,
            email=spec.email,
            name=None,
            normalized_email=spec.email.strip().lower(),
            email_verified=spec.email_verified,
        )


@dataclass(frozen=True)
class PersistedRows:
    users: int
    credentials: int
    external_identities: int


def _build_login_use_case(
    *,
    session: AsyncSession,
    verifier: ExternalIdentityVerifier,
) -> LoginCommandUseCase:
    return LoginCommandUseCase(
        identity_verifier=verifier,
        login_synchronizer=SqlAlchemyExternalIdentityLoginSynchronizer(session),
        credential_repository=SqlAlchemyCredentialRepository(session),
        user_provisioner=_ProvisionUserPortAdapter(
            build_resolve_user_for_login_command_use_case(session)
        ),
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=build_refresh_token_service(),
    )


async def _login(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    verifier: ExternalIdentityVerifier,
    provider_token: str,
) -> None:
    async with session_factory() as session:
        transaction = await session.begin()
        use_case = _build_login_use_case(session=session, verifier=verifier)
        await use_case.execute(
            LoginCommand(
                provider_token=provider_token,
                terms_accepted=True,
                privacy_accepted=True,
            )
        )
        await transaction.commit()


async def _count_rows(session_factory: async_sessionmaker[AsyncSession]) -> PersistedRows:
    async with session_factory() as session:
        users = await count_persisted_users(session)
        credentials = await session.scalar(
            select(func.count()).select_from(auth_orm.UserCredential)
        )
        external_identities = await session.scalar(
            select(func.count()).select_from(auth_orm.ExternalIdentity)
        )
    return PersistedRows(
        users=users,
        credentials=_require_count(credentials),
        external_identities=_require_count(external_identities),
    )


def _require_count(value: int | None) -> int:
    if value is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return value


def _write_evidence(name: str, content: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    path.write_text(content + "\n", encoding="utf-8")
    return path


async def test_verified_same_email_links_into_single_user(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    verifier = ScriptedExternalIdentityVerifier(
        specs={
            "google-token": IdentitySpec(
                subject="google-subject",
                provider="google",
                email="linked@example.com",
            ),
            "apple-token": IdentitySpec(
                subject="apple-subject",
                provider="apple",
                email="linked@example.com",
            ),
        }
    )

    await _login(
        session_factory=postgres_session_factory,
        verifier=verifier,
        provider_token="google-token",
    )
    await _login(
        session_factory=postgres_session_factory,
        verifier=verifier,
        provider_token="apple-token",
    )

    rows = await _count_rows(postgres_session_factory)
    assert rows == PersistedRows(users=1, credentials=1, external_identities=2)

    summary = (
        f"unique_user_count={rows.users} "
        f"credential_count={rows.credentials} "
        f"external_identity_count={rows.external_identities}"
    )
    evidence_path = _write_evidence("task-5-same-email-green.log", summary)
    assert evidence_path.is_file()
    with capsys.disabled():
        print(summary)


async def test_different_emails_create_separate_users(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    verifier = ScriptedExternalIdentityVerifier(
        specs={
            "first-token": IdentitySpec(
                subject="first-subject",
                provider="google",
                email="first@example.com",
            ),
            "second-token": IdentitySpec(
                subject="second-subject",
                provider="google",
                email="second@example.com",
            ),
        }
    )

    await _login(
        session_factory=postgres_session_factory,
        verifier=verifier,
        provider_token="first-token",
    )
    await _login(
        session_factory=postgres_session_factory,
        verifier=verifier,
        provider_token="second-token",
    )

    rows = await _count_rows(postgres_session_factory)
    assert rows == PersistedRows(users=2, credentials=2, external_identities=2)


async def test_unverified_second_email_does_not_merge(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    verifier = ScriptedExternalIdentityVerifier(
        specs={
            "verified-token": IdentitySpec(
                subject="verified-subject",
                provider="google",
                email="merge@example.com",
            ),
            "unverified-token": IdentitySpec(
                subject="unverified-subject",
                provider="apple",
                email="merge@example.com",
                email_verified=False,
            ),
        }
    )

    await _login(
        session_factory=postgres_session_factory,
        verifier=verifier,
        provider_token="verified-token",
    )
    rows_before = await _count_rows(postgres_session_factory)

    with pytest.raises(AuthenticationError):
        await _login(
            session_factory=postgres_session_factory,
            verifier=verifier,
            provider_token="unverified-token",
        )

    rows_after = await _count_rows(postgres_session_factory)
    assert rows_after == rows_before
    assert rows_after == PersistedRows(users=1, credentials=1, external_identities=1)

    summary = (
        f"unverified_email_rejected users={rows_after.users} "
        f"credentials={rows_after.credentials} "
        f"external_identities={rows_after.external_identities}"
    )
    evidence_path = _write_evidence("task-5-unverified-email-rejected.log", summary)
    assert evidence_path.is_file()
    with capsys.disabled():
        print(summary)
