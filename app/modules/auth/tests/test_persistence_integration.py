from datetime import UTC, datetime, timedelta

import anyio
import pytest
from anyio import Path as AnyioPath
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.domain.model import RefreshToken as DomainRefreshToken
from app.modules.auth.infrastructure.persistence import mapper as auth_mapper
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from tests.support.users_persistence import count_persisted_users, create_persisted_user

EVIDENCE_DIR = ".omo/evidence/auth-users-bc-prd-completion"


async def test_postgres_fixture_persists_and_rolls_back_auth_users_rows(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with postgres_session_factory() as session:
        transaction = await session.begin()
        try:
            user = await create_persisted_user(
                session,
                name="테스트 사용자",
                email="fixture@example.com",
            )
            credentials = await SqlAlchemyCredentialRepository(
                session
            ).create_for_external_identity(
                identity=ExternalIdentity.create(
                    issuer="google",
                    subject="firebase-subject",
                    provider="google",
                    email=user.email,
                    name=user.name,
                ),
                user_id=user.id,
                logged_in_at=datetime.now(UTC),
            )
            session_id = await SqlAlchemyCredentialRepository(session).create_session(
                credentials_id=credentials.credentials_id,
            )
            await SqlAlchemyCredentialRepository(session).save_refresh_token(
                credentials_id=credentials.credentials_id,
                session_id=session_id,
                token_hash="postgres-fixture-refresh-token-hash",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )

            credentials_count = await session.scalar(
                select(func.count()).select_from(auth_orm.UserCredential)
            )
            external_identities_count = await session.scalar(
                select(func.count()).select_from(auth_orm.ExternalIdentity)
            )
            refresh_tokens_count = await session.scalar(
                select(func.count()).select_from(auth_orm.RefreshToken)
            )

            assert await count_persisted_users(session) == 1
            assert credentials_count == 1
            assert external_identities_count == 1
            assert refresh_tokens_count == 1
        finally:
            await transaction.rollback()

    async with postgres_session_factory() as session:
        users_after_rollback = await count_persisted_users(session)
        credentials_after_rollback = await session.scalar(
            select(func.count()).select_from(auth_orm.UserCredential)
        )
        external_identities_after_rollback = await session.scalar(
            select(func.count()).select_from(auth_orm.ExternalIdentity)
        )
        refresh_tokens_after_rollback = await session.scalar(
            select(func.count()).select_from(auth_orm.RefreshToken)
        )

    assert users_after_rollback == 0
    assert credentials_after_rollback == 0
    assert external_identities_after_rollback == 0
    assert refresh_tokens_after_rollback == 0

    with capsys.disabled():
        print(
            "postgres integration verified: "
            "inside_transaction users=1 credentials=1 external_identities=1 refresh_tokens=1; "
            "after_rollback users=0 credentials=0 external_identities=0 refresh_tokens=0"
        )


async def _setup_refresh_token(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Create a user, credentials, session, and refresh token; return the token_hash."""
    async with session_factory() as session, session.begin():
        user = await create_persisted_user(
            session,
            name="로테이션 테스트",
            email="rotate@example.com",
        )
        repo = SqlAlchemyCredentialRepository(session)
        credentials = await repo.create_for_external_identity(
            identity=ExternalIdentity.create(
                issuer="google",
                subject="rotate-subject",
                provider="google",
                email=user.email,
                name=user.name,
            ),
            user_id=user.id,
            logged_in_at=datetime.now(UTC),
        )
        session_id = await repo.create_session(
            credentials_id=credentials.credentials_id,
        )
        await repo.save_refresh_token(
            credentials_id=credentials.credentials_id,
            session_id=session_id,
            token_hash="original-token-hash",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    return "original-token-hash"


async def test_concurrent_rotate_refresh_token_exactly_one_wins(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two concurrent rotate_refresh_token calls on the same token_hash:
    exactly one returns a SessionCredential, the other raises AuthenticationError.
    Final DB has exactly one (the new) refresh token for that session.
    """
    token_hash = await _setup_refresh_token(postgres_session_factory)

    outcomes: list[str] = []
    barrier = anyio.Event()

    async def _rotate(new_hash: str) -> None:
        # Both tasks reach the barrier before either executes rotate
        await barrier.wait()
        async with postgres_session_factory() as session, session.begin():
            repo = SqlAlchemyCredentialRepository(session)
            try:
                await repo.rotate_refresh_token(
                    token_hash=token_hash,
                    new_token_hash=new_hash,
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
                outcomes.append("rotated")
            except (AuthenticationError, SQLAlchemyError):
                outcomes.append("rejected")

    async with anyio.create_task_group() as tg:
        tg.start_soon(_rotate, "new-token-hash-a")
        tg.start_soon(_rotate, "new-token-hash-b")
        barrier.set()

    assert sorted(outcomes) == ["rejected", "rotated"]

    # Exactly one new refresh token must survive in DB
    async with postgres_session_factory() as session:
        remaining = await session.scalar(select(func.count()).select_from(auth_orm.RefreshToken))
    assert remaining == 1

    summary = (
        f"concurrent refresh rotation verified: "
        f"outcomes={sorted(outcomes)} remaining_refresh_tokens={remaining}"
    )
    with capsys.disabled():
        print(summary)

    evidence_dir = AnyioPath(EVIDENCE_DIR)
    await evidence_dir.mkdir(parents=True, exist_ok=True)
    await (evidence_dir / "task-7-refresh-race-green.log").write_text(
        f"# Todo 7 acceptance — atomic refresh rotation\n{summary}\n",
        encoding="utf-8",
    )


async def test_rotate_refresh_token_insert_failure_restores_original_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Force new_token_hash to collide with an existing token_hash (UNIQUE violation).
    The INSERT fails -> whole tx rolls back -> original token is still present.
    """
    token_hash = await _setup_refresh_token(postgres_session_factory)

    # Plant a second token with the hash we'll try to insert, causing a collision.
    async with postgres_session_factory() as session, session.begin():
        existing_rt = await session.scalar(
            select(auth_orm.RefreshToken).where(auth_orm.RefreshToken.token_hash == token_hash)
        )
        assert existing_rt is not None
        collision_token = DomainRefreshToken.create(
            credentials_id=existing_rt.credentials_id,
            session_id=existing_rt.session_id,
            token_hash="collision-hash",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        session.add(auth_mapper.refresh_token_to_record(collision_token))

    # Attempt rotation with new_token_hash == "collision-hash" -> IntegrityError on INSERT.
    # The error surfaces at transaction commit (when the `async with session.begin()` exits),
    # so we catch it outside both context managers.
    raised: Exception | None = None
    try:
        async with postgres_session_factory() as session, session.begin():
            repo = SqlAlchemyCredentialRepository(session)
            await repo.rotate_refresh_token(
                token_hash=token_hash,
                new_token_hash="collision-hash",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
    except (IntegrityError, SQLAlchemyError) as exc:
        raised = exc

    assert raised is not None, "Expected IntegrityError from duplicate token_hash"

    # After rollback, original token must still be present
    async with postgres_session_factory() as session:
        original_count = await session.scalar(
            select(func.count())
            .select_from(auth_orm.RefreshToken)
            .where(auth_orm.RefreshToken.token_hash == token_hash)
        )
    assert original_count == 1, "Original token must survive after INSERT rollback"

    summary = (
        f"rollback verified: IntegrityError raised, original token_hash='{token_hash}' "
        f"still present (count={original_count})"
    )
    with capsys.disabled():
        print(summary)

    evidence_dir = AnyioPath(EVIDENCE_DIR)
    await evidence_dir.mkdir(parents=True, exist_ok=True)
    await (evidence_dir / "task-7-refresh-rollback.log").write_text(
        f"# Todo 7 rollback — duplicate new-token-hash forces IntegrityError + restores old token\n"
        f"{summary}\n",
        encoding="utf-8",
    )
