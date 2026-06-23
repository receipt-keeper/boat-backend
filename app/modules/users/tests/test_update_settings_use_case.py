from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.users.application.commands.resolve_user_for_login.command import (
    ResolveUserForLoginCommand,
)
from app.modules.users.application.commands.resolve_user_for_login.use_case import (
    ResolveUserForLoginCommandUseCase,
)
from app.modules.users.application.commands.update_settings.command import (
    UpdateSettingsCommand,
)
from app.modules.users.application.commands.update_settings.use_case import (
    UpdateSettingsCommandUseCase,
)
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository


async def _create_user(session: AsyncSession, *, email: str) -> UUID:
    repository = SqlAlchemyUserRepository(session)
    unit_of_work = SqlAlchemyUnitOfWork(session)
    user = await ResolveUserForLoginCommandUseCase(
        user_repository=repository,
        unit_of_work=unit_of_work,
    ).execute(
        ResolveUserForLoginCommand(
            name="동의 시각",
            email=email,
            profile_image_url=None,
            terms_accepted=True,
            privacy_accepted=True,
        )
    )
    return user.user_id


async def _opt_in_marketing(session: AsyncSession, *, user_id: UUID) -> datetime:
    repository = SqlAlchemyUserRepository(session)
    unit_of_work = SqlAlchemyUnitOfWork(session)
    await UpdateSettingsCommandUseCase(
        user_repository=repository,
        unit_of_work=unit_of_work,
    ).execute(UpdateSettingsCommand(user_id=user_id, marketing_consent=True))
    state = await repository.find_account_state(user_id=user_id)
    assert state is not None
    timestamp = state.settings.marketing_consent_updated_at
    assert timestamp is not None
    return timestamp


async def test_update_settings_records_marketing_consent_timestamp_on_opt_in(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user_id = await _create_user(session, email="consent-optin@example.com")

        await UpdateSettingsCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(UpdateSettingsCommand(user_id=user_id, marketing_consent=True))
        state = await repository.find_account_state(user_id=user_id)

    assert state is not None
    assert state.settings.marketing_consent is True
    assert state.settings.marketing_consent_updated_at is not None


async def test_update_settings_preserves_marketing_timestamp_when_value_is_unchanged(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user_id = await _create_user(session, email="consent-noop@example.com")
        optin_ts = await _opt_in_marketing(session, user_id=user_id)

        await UpdateSettingsCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(UpdateSettingsCommand(user_id=user_id, marketing_consent=True))
        state = await repository.find_account_state(user_id=user_id)

    assert state is not None
    assert state.settings.marketing_consent is True
    assert state.settings.marketing_consent_updated_at == optin_ts


async def test_update_settings_preserves_marketing_timestamp_when_only_notification_changes(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user_id = await _create_user(session, email="notification-only@example.com")
        optin_ts = await _opt_in_marketing(session, user_id=user_id)

        await UpdateSettingsCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(UpdateSettingsCommand(user_id=user_id, notification_enabled=False))
        state = await repository.find_account_state(user_id=user_id)

    assert state is not None
    assert state.settings.notification_enabled is False
    assert state.settings.marketing_consent_updated_at == optin_ts


async def test_update_settings_refreshes_marketing_timestamp_on_opt_out(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user_id = await _create_user(session, email="consent-optout@example.com")
        optin_ts = await _opt_in_marketing(session, user_id=user_id)

        await UpdateSettingsCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(UpdateSettingsCommand(user_id=user_id, marketing_consent=False))
        state = await repository.find_account_state(user_id=user_id)

    assert state is not None
    assert state.settings.marketing_consent is False
    assert state.settings.marketing_consent_updated_at is not None
    assert state.settings.marketing_consent_updated_at > optin_ts
