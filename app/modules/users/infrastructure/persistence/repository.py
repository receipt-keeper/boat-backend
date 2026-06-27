from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.exceptions import NotFoundError
from app.modules.users.application.ports.user_repository import (
    CreateUserAccountState,
    UserAccountState,
    UserRepository,
)
from app.modules.users.domain.model import User, UserSettings
from app.modules.users.infrastructure.persistence import mapper, orm


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str | None, email: str | None) -> User:
        user = User.create(name=name, email=email)
        record = mapper.user_to_record(user)
        self._session.add(record)
        await self._session.flush()
        return user

    async def delete_by_id(self, *, user_id: UUID) -> None:
        await self.delete_account_state(user_id=user_id)

    async def find_account_state(self, *, user_id: UUID) -> UserAccountState | None:
        user_record = await self._session.get(orm.User, user_id)
        if user_record is None:
            return None
        return await self._account_state(user_record=user_record)

    async def create_account_state(self, *, state: CreateUserAccountState) -> UserAccountState:
        user_record = mapper.user_to_record(state.user)
        self._session.add(user_record)
        self._session.add(mapper.settings_to_record(state.settings))
        await self._session.flush()
        return UserAccountState(
            user=state.user,
            settings=state.settings,
        )

    async def update_settings(self, *, settings: UserSettings) -> UserSettings:
        record = await self._session.get(orm.UserSettings, settings.id)
        if record is None:
            record = mapper.settings_to_record(settings)
            self._session.add(record)
            await self._session.flush()
            return settings

        record.terms_version = settings.terms_version
        record.privacy_version = settings.privacy_version
        record.terms_accepted_at = settings.terms_accepted_at
        record.privacy_accepted_at = settings.privacy_accepted_at
        await self._session.flush()
        return mapper.settings_to_domain(record)

    async def update_profile_image_url(
        self,
        *,
        user_id: UUID,
        profile_image_url: str | None,
    ) -> User:
        record = await self._session.get(orm.User, user_id)
        if record is None:
            raise NotFoundError("사용자를 찾을 수 없습니다.")
        record.profile_image_url = profile_image_url
        await self._session.flush()
        return mapper.user_to_domain(record)

    async def delete_account_state(self, *, user_id: UUID) -> None:
        await self._session.execute(
            delete(orm.UserSettings).where(orm.UserSettings.user_id == user_id)
        )
        await self._session.execute(delete(orm.User).where(orm.User.id == user_id))

    async def _account_state(
        self,
        *,
        user_record: orm.User,
    ) -> UserAccountState:
        settings_record = await self._session.get(orm.UserSettings, user_record.id)
        settings = (
            UserSettings.create(user_id=user_record.id)
            if settings_record is None
            else mapper.settings_to_domain(settings_record)
        )
        return UserAccountState(
            user=mapper.user_to_domain(user_record),
            settings=settings,
        )
