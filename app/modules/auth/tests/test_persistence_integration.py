from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from tests.support.users_persistence import count_persisted_users, create_persisted_user


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
                    issuer="firebase",
                    subject="firebase-subject",
                    provider="google",
                    email=user.email,
                    name=user.name,
                ),
                user_id=user.id,
                logged_in_at=datetime.now(UTC),
            )
            await SqlAlchemyCredentialRepository(session).save_refresh_token(
                credentials_id=credentials.credentials_id,
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
