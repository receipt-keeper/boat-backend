from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.application.constants import AUTHENTICATION_FAILED_MESSAGE
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity, RefreshToken, UserCredential
from app.modules.auth.infrastructure.persistence import mapper, orm

SessionProvider = AsyncSession | async_sessionmaker[AsyncSession]


class SqlAlchemyCredentialRepository(CredentialRepository):
    def __init__(self, session_provider: SessionProvider) -> None:
        self._session_provider = session_provider

    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        async with self._session(transactional=False) as session:
            credentials = await self._get_credentials_by_identity(
                session=session,
                issuer=identity.issuer.value,
                subject=identity.subject.value,
            )
            if credentials is None:
                return None
            return mapper.user_credential_to_domain(credentials)

    async def create_for_external_identity(
        self,
        *,
        identity: ExternalIdentity,
        user_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        async with self._session(transactional=True) as session:
            credentials = UserCredential.create(user_id=user_id, last_login_at=logged_in_at)
            credentials_record = orm.UserCredential(
                id=credentials.credentials_id,
                user_id=credentials.user_id,
                role=credentials.role.value,
                last_login_at=credentials.last_login_at,
            )
            session.add(credentials_record)
            await session.flush()

            session.add(
                mapper.external_identity_to_record(
                    identity,
                    credentials_id=credentials.credentials_id,
                )
            )
            return credentials

    async def record_login(
        self,
        *,
        credentials_id: UUID,
        logged_in_at: datetime,
    ) -> UserCredential:
        async with self._session(transactional=True) as session:
            credentials = await session.get(orm.UserCredential, credentials_id)
            if credentials is None:
                raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)
            credentials.last_login_at = logged_in_at
            return mapper.user_credential_to_domain(credentials)

    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        refresh_token = RefreshToken.create(
            credentials_id=credentials_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        async with self._session(transactional=True) as session:
            session.add(mapper.refresh_token_to_record(refresh_token))

    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> UserCredential:
        async with self._session(transactional=True) as session:
            refresh_token = await self._get_valid_refresh_token(
                session=session,
                token_hash=token_hash,
            )
            if refresh_token is None:
                raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)

            credentials = await session.get(orm.UserCredential, refresh_token.credentials_id)
            if credentials is None:
                raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)

            await session.delete(refresh_token)
            session.add(
                mapper.refresh_token_to_record(
                    RefreshToken.create(
                        credentials_id=credentials.id,
                        token_hash=new_token_hash,
                        expires_at=expires_at,
                    )
                )
            )
            return mapper.user_credential_to_domain(credentials)

    async def revoke_refresh_token(self, *, token_hash: str) -> None:
        async with self._session(transactional=True) as session:
            await session.execute(
                delete(orm.RefreshToken).where(orm.RefreshToken.token_hash == token_hash)
            )

    async def exists_active_credential(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> bool:
        async with self._session(transactional=False) as session:
            statement = select(orm.UserCredential.id).where(
                orm.UserCredential.id == credentials_id,
                orm.UserCredential.user_id == user_id,
            )
            return await session.scalar(statement) is not None

    async def delete_account_auth_state(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        async with self._session(transactional=True) as session:
            await session.execute(
                delete(orm.RefreshToken).where(orm.RefreshToken.credentials_id == credentials_id)
            )
            await session.execute(
                delete(orm.ExternalIdentity).where(
                    orm.ExternalIdentity.credentials_id == credentials_id
                )
            )
            await session.execute(
                delete(orm.UserCredential).where(
                    orm.UserCredential.id == credentials_id,
                    orm.UserCredential.user_id == user_id,
                )
            )

    @asynccontextmanager
    async def _session(self, *, transactional: bool) -> AsyncIterator[AsyncSession]:
        if isinstance(self._session_provider, AsyncSession):
            yield self._session_provider
            return

        async with self._session_provider() as session:
            if not transactional:
                yield session
                return
            async with session.begin():
                yield session

    async def _get_credentials_by_identity(
        self,
        *,
        session: AsyncSession,
        issuer: str,
        subject: str,
    ) -> orm.UserCredential | None:
        statement = (
            select(orm.UserCredential)
            .join(
                orm.ExternalIdentity,
                orm.ExternalIdentity.credentials_id == orm.UserCredential.id,
            )
            .where(
                orm.ExternalIdentity.issuer == issuer,
                orm.ExternalIdentity.subject == subject,
            )
        )
        return await session.scalar(statement)

    async def _get_valid_refresh_token(
        self,
        *,
        session: AsyncSession,
        token_hash: str,
    ) -> orm.RefreshToken | None:
        statement = select(orm.RefreshToken).where(
            orm.RefreshToken.token_hash == token_hash,
            orm.RefreshToken.expires_at > datetime.now(UTC),
        )
        return await session.scalar(statement)
