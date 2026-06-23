from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.users.application.ports.user_repository import (
    CreateUserAccountState,
    UserAccountState,
    UserRepository,
)
from app.modules.users.domain.model import User, UserEntitlement, UserPushToken, UserSettings
from app.modules.users.infrastructure.persistence import mapper, orm

SessionProvider = AsyncSession | async_sessionmaker[AsyncSession]


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session_provider: SessionProvider) -> None:
        self._session_provider = session_provider

    async def create(self, *, name: str | None, email: str | None) -> User:
        user = User.create(name=name, email=email)
        async with self._session(transactional=True) as session:
            record = mapper.user_to_record(user)
            session.add(record)
            await session.flush()
        return user

    async def delete_by_id(self, *, user_id: UUID) -> None:
        await self.delete_account_state(user_id=user_id)

    async def find_account_state(self, *, user_id: UUID) -> UserAccountState | None:
        async with self._session(transactional=False) as session:
            user_record = await session.get(orm.User, user_id)
            if user_record is None:
                return None
            return await self._account_state(session=session, user_record=user_record)

    async def create_account_state(self, *, state: CreateUserAccountState) -> UserAccountState:
        async with self._session(transactional=True) as session:
            user_record = mapper.user_to_record(state.user)
            session.add(user_record)
            session.add(mapper.settings_to_record(state.settings))
            session.add(mapper.entitlement_to_record(state.entitlement))
            await session.flush()
            return UserAccountState(
                user=state.user,
                settings=state.settings,
                entitlement=state.entitlement,
                push_tokens=(),
            )

    async def update_settings(self, *, settings: UserSettings) -> UserSettings:
        async with self._session(transactional=True) as session:
            record = await session.get(orm.UserSettings, settings.id)
            if record is None:
                record = mapper.settings_to_record(settings)
                session.add(record)
                await session.flush()
                return settings

            record.notification_enabled = settings.notification_enabled
            record.marketing_consent = settings.marketing_consent
            record.terms_version = settings.terms_version
            record.privacy_version = settings.privacy_version
            record.terms_accepted_at = settings.terms_accepted_at
            record.privacy_accepted_at = settings.privacy_accepted_at
            record.marketing_consent_updated_at = settings.marketing_consent_updated_at
            await session.flush()
            return mapper.settings_to_domain(record)

    async def upsert_push_token(self, *, push_token: UserPushToken) -> UserPushToken:
        async with self._session(transactional=True) as session:
            statement = select(orm.UserPushToken).where(
                orm.UserPushToken.user_id == push_token.user_id,
                orm.UserPushToken.device_id == push_token.device_id,
            )
            record = await session.scalar(statement)
            if record is None:
                record = mapper.push_token_to_record(push_token)
                session.add(record)
                await session.flush()
                return push_token

            record.fcm_token = push_token.fcm_token
            record.platform = push_token.platform.value
            await session.flush()
            return mapper.push_token_to_domain(record)

    async def delete_push_token(self, *, user_id: UUID, device_id: str) -> None:
        async with self._session(transactional=True) as session:
            await session.execute(
                delete(orm.UserPushToken).where(
                    orm.UserPushToken.user_id == user_id,
                    orm.UserPushToken.device_id == device_id,
                )
            )

    async def delete_account_state(self, *, user_id: UUID) -> None:
        async with self._session(transactional=True) as session:
            await session.execute(
                delete(orm.UserPushToken).where(orm.UserPushToken.user_id == user_id)
            )
            await session.execute(
                delete(orm.UserSettings).where(orm.UserSettings.user_id == user_id)
            )
            await session.execute(
                delete(orm.UserEntitlement).where(orm.UserEntitlement.user_id == user_id)
            )
            await session.execute(delete(orm.User).where(orm.User.id == user_id))

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

    async def _account_state(
        self,
        *,
        session: AsyncSession,
        user_record: orm.User,
    ) -> UserAccountState:
        settings_record = await session.get(orm.UserSettings, user_record.id)
        entitlement_record = await session.get(orm.UserEntitlement, user_record.id)
        push_token_records = await session.scalars(
            select(orm.UserPushToken).where(orm.UserPushToken.user_id == user_record.id)
        )
        settings = (
            UserSettings.create(user_id=user_record.id)
            if settings_record is None
            else mapper.settings_to_domain(settings_record)
        )
        entitlement = (
            UserEntitlement.create(user_id=user_record.id)
            if entitlement_record is None
            else mapper.entitlement_to_domain(entitlement_record)
        )
        return UserAccountState(
            user=mapper.user_to_domain(user_record),
            settings=settings,
            entitlement=entitlement,
            push_tokens=tuple(mapper.push_token_to_domain(record) for record in push_token_records),
        )
