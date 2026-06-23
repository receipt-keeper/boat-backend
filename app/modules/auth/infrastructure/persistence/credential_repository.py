from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.ports.credential_repository import (
    CredentialRepository,
    SessionCredential,
)
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import (
    AuthSession,
    ExternalIdentity,
    RefreshToken,
    UserCredential,
)
from app.modules.auth.infrastructure.persistence import mapper, orm


class SqlAlchemyCredentialRepository(CredentialRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_external_identity(
        self,
        *,
        identity: ExternalIdentity,
    ) -> UserCredential | None:
        statement = (
            select(orm.UserCredential)
            .join(
                orm.ExternalIdentity,
                orm.ExternalIdentity.credentials_id == orm.UserCredential.id,
            )
            .where(
                orm.ExternalIdentity.issuer == identity.issuer.value,
                orm.ExternalIdentity.subject == identity.subject.value,
            )
        )
        credentials = await self._session.scalar(statement)
        if credentials is None:
            return None
        return mapper.user_credential_to_domain(credentials)

    async def find_by_verified_email(self, *, canonical_email: str) -> UserCredential | None:
        statement = (
            select(orm.UserCredential)
            .join(
                orm.ExternalIdentity,
                orm.ExternalIdentity.credentials_id == orm.UserCredential.id,
            )
            .where(
                orm.ExternalIdentity.normalized_email == canonical_email,
                orm.ExternalIdentity.email_verified.is_(True),
            )
        )
        credentials = await self._session.scalar(statement)
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
        credentials = UserCredential.create(user_id=user_id, last_login_at=logged_in_at)
        self._session.add(mapper.user_credential_to_record(credentials))
        await self._session.flush()

        self._session.add(
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
        credentials = await self._session.get(orm.UserCredential, credentials_id)
        if credentials is None:
            raise AuthenticationError()
        credentials.last_login_at = logged_in_at
        return mapper.user_credential_to_domain(credentials)

    async def find_credential_by_user_id(self, *, user_id: UUID) -> UserCredential | None:
        statement = select(orm.UserCredential).where(
            orm.UserCredential.user_id == user_id,
        )
        credentials = await self._session.scalar(statement)
        if credentials is None:
            return None
        return mapper.user_credential_to_domain(credentials)

    async def attach_external_identity(
        self,
        *,
        credentials_id: UUID,
        identity: ExternalIdentity,
    ) -> None:
        self._session.add(
            mapper.external_identity_to_record(
                identity,
                credentials_id=credentials_id,
            )
        )

    async def create_session(self, *, credentials_id: UUID) -> UUID:
        auth_session = AuthSession.create(credentials_id=credentials_id)
        self._session.add(mapper.auth_session_to_record(auth_session))
        await self._session.flush()
        return auth_session.session_id

    async def save_refresh_token(
        self,
        *,
        credentials_id: UUID,
        session_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        refresh_token = RefreshToken.create(
            credentials_id=credentials_id,
            session_id=session_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(mapper.refresh_token_to_record(refresh_token))

    async def rotate_refresh_token(
        self,
        *,
        token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> SessionCredential:
        result = await self._session.execute(
            delete(orm.RefreshToken)
            .where(orm.RefreshToken.token_hash == token_hash)
            .returning(
                orm.RefreshToken.id,
                orm.RefreshToken.credentials_id,
                orm.RefreshToken.session_id,
                orm.RefreshToken.expires_at,
            )
        )
        row = result.first()
        if row is None:
            raise AuthenticationError()

        _rt_id, rt_credentials_id, rt_session_id, rt_expires_at = row
        if rt_session_id is None:
            raise AuthenticationError()

        if rt_expires_at <= datetime.now(UTC):
            raise AuthenticationError()

        auth_session = await self._session.get(orm.AuthSession, rt_session_id)
        if auth_session is None or auth_session.revoked_at is not None:
            raise AuthenticationError()

        credentials = await self._session.get(orm.UserCredential, rt_credentials_id)
        if credentials is None or credentials.id != auth_session.credentials_id:
            raise AuthenticationError()

        self._session.add(
            mapper.refresh_token_to_record(
                RefreshToken.create(
                    credentials_id=credentials.id,
                    session_id=auth_session.id,
                    token_hash=new_token_hash,
                    expires_at=expires_at,
                )
            )
        )
        return SessionCredential(
            credentials=mapper.user_credential_to_domain(credentials),
            session_id=auth_session.id,
        )

    async def revoke_session_by_refresh_token(self, *, token_hash: str) -> None:
        statement = select(orm.RefreshToken).where(
            orm.RefreshToken.token_hash == token_hash,
            orm.RefreshToken.expires_at > datetime.now(UTC),
        )
        refresh_token = await self._session.scalar(statement)
        if refresh_token is None:
            return
        if refresh_token.session_id is None:
            await self._session.delete(refresh_token)
            return

        auth_session = await self._session.get(orm.AuthSession, refresh_token.session_id)
        if auth_session is not None:
            auth_session.revoked_at = datetime.now(UTC)
        await self._session.execute(
            delete(orm.RefreshToken).where(orm.RefreshToken.session_id == refresh_token.session_id)
        )

    async def exists_active_credential(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> bool:
        statement = select(orm.UserCredential.id).where(
            orm.UserCredential.id == credentials_id,
            orm.UserCredential.user_id == user_id,
        )
        return await self._session.scalar(statement) is not None

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        statement = (
            select(orm.AuthSession.id)
            .join(
                orm.UserCredential,
                orm.UserCredential.id == orm.AuthSession.credentials_id,
            )
            .where(
                orm.UserCredential.id == credentials_id,
                orm.UserCredential.user_id == user_id,
                orm.AuthSession.id == session_id,
                orm.AuthSession.revoked_at.is_(None),
            )
        )
        return await self._session.scalar(statement) is not None

    async def delete_account_auth_state(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
    ) -> None:
        owned_credentials_id = await self._session.scalar(
            select(orm.UserCredential.id).where(
                orm.UserCredential.id == credentials_id,
                orm.UserCredential.user_id == user_id,
            )
        )
        if owned_credentials_id is None:
            return

        await self._session.execute(
            delete(orm.RefreshToken).where(orm.RefreshToken.credentials_id == owned_credentials_id)
        )
        await self._session.execute(
            delete(orm.AuthSession).where(orm.AuthSession.credentials_id == owned_credentials_id)
        )
        await self._session.execute(
            delete(orm.ExternalIdentity).where(
                orm.ExternalIdentity.credentials_id == owned_credentials_id
            )
        )
        await self._session.execute(
            delete(orm.UserCredential).where(
                orm.UserCredential.id == owned_credentials_id,
            )
        )
