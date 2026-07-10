from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.exceptions import NotFoundError
from app.modules.users.application.ports.user_repository import (
    CreateUserAccountState,
    ListUserNotificationCandidatesQuery,
    UserAccountState,
    UserNotificationCandidate,
    UserNotificationCandidateCursor,
    UserNotificationCandidatePage,
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
        current = mapper.user_to_domain(record)
        updated = current.update_profile_image_url(profile_image_url=profile_image_url)
        record.profile_image_url = updated.profile_image_url
        await self._session.flush()
        return updated

    async def delete_account_state(self, *, user_id: UUID) -> None:
        await self._session.execute(
            delete(orm.UserSettings).where(orm.UserSettings.user_id == user_id)
        )
        await self._session.execute(delete(orm.User).where(orm.User.id == user_id))

    async def list_notification_candidates(
        self,
        *,
        query: ListUserNotificationCandidatesQuery,
    ) -> UserNotificationCandidatePage:
        statement = (
            select(orm.User)
            .order_by(orm.User.created_at.asc(), orm.User.id.asc())
            .limit(query.batch_size + 1)
        )
        if query.created_after is not None:
            statement = statement.where(orm.User.created_at >= query.created_after)
        if query.created_before is not None:
            statement = statement.where(orm.User.created_at < query.created_before)
        if query.cursor is not None:
            statement = statement.where(
                or_(
                    orm.User.created_at > query.cursor.created_at,
                    and_(
                        orm.User.created_at == query.cursor.created_at,
                        orm.User.id > query.cursor.user_id,
                    ),
                )
            )

        result = await self._session.execute(statement)
        records = tuple(result.scalars().all())
        page_records = records[: query.batch_size]
        candidates = tuple(
            candidate
            for record in page_records
            for candidate in _notification_candidates(record=record, query=query)
        )
        next_cursor = (
            UserNotificationCandidateCursor(
                created_at=page_records[-1].created_at,
                user_id=page_records[-1].id,
            )
            if len(records) > query.batch_size and page_records
            else None
        )
        return UserNotificationCandidatePage(
            candidates=candidates,
            next_cursor=next_cursor,
        )

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


def _notification_candidates(
    *,
    record: orm.User,
    query: ListUserNotificationCandidatesQuery,
) -> tuple[UserNotificationCandidate, ...]:
    days_since_joined = (query.as_of - record.created_at.date()).days
    return (
        UserNotificationCandidate(
            user_id=record.id,
            created_at=record.created_at,
            days_since_joined=days_since_joined,
            cursor_created_at=record.created_at,
            cursor_id=record.id,
        ),
    )
