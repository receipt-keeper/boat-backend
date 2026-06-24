from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.users.application.commands.delete_push_token.command import (
    DeletePushTokenCommand,
)
from app.modules.users.application.commands.delete_push_token.use_case import (
    DeletePushTokenCommandUseCase,
)
from app.modules.users.application.commands.register_push_token.command import (
    RegisterPushTokenCommand,
)
from app.modules.users.application.commands.register_push_token.use_case import (
    RegisterPushTokenCommandUseCase,
)
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
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.commands.withdrawal_cleanup.use_case import (
    WithdrawalCleanupCommandUseCase,
)
from app.modules.users.application.queries.current_user_profile.query import (
    CurrentUserProfileQuery,
)
from app.modules.users.application.queries.current_user_profile.use_case import (
    CurrentUserProfileQueryUseCase,
)
from app.modules.users.infrastructure.persistence import orm
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository

CountableUsersTable = (
    type[orm.User] | type[orm.UserSettings] | type[orm.UserEntitlement] | type[orm.UserPushToken]
)


async def test_resolve_user_for_login_creates_profile_email_value(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        use_case = ResolveUserForLoginCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        )

        result = await use_case.execute(
            ResolveUserForLoginCommand(
                name="첫 사용자",
                email="person@example.com",
                profile_image_url="https://example.com/a.png",
                terms_accepted=True,
                privacy_accepted=True,
            )
        )
        state = await repository.find_account_state(user_id=result.user_id)

    async with postgres_session_factory() as session:
        users_count = await _count(session, orm.User)
        settings_count = await _count(session, orm.UserSettings)
        entitlement_count = await _count(session, orm.UserEntitlement)

    assert state is not None
    assert state.user.email is not None
    assert state.user.email.value == "person@example.com"
    assert not hasattr(state.user, "normalized_email")
    assert result.free_analysis_tokens_remaining == 0
    assert result.notification_enabled is True
    assert result.marketing_consent is False
    assert users_count == 1
    assert settings_count == 1
    assert entitlement_count == 1


async def test_profile_settings_push_and_withdrawal_surface(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user = await ResolveUserForLoginCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(
            ResolveUserForLoginCommand(
                name="표면 테스트",
                email="surface@example.com",
                profile_image_url=None,
                initial_free_analysis_tokens=3,
                terms_accepted=True,
                privacy_accepted=True,
            )
        )

        settings = await UpdateSettingsCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(
            UpdateSettingsCommand(
                user_id=user.user_id,
                notification_enabled=False,
                marketing_consent=True,
            )
        )
        registered = await RegisterPushTokenCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(
            RegisterPushTokenCommand(
                user_id=user.user_id,
                device_id="device-1",
                fcm_token="token-a",
                platform="ios",
            )
        )
        updated = await RegisterPushTokenCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(
            RegisterPushTokenCommand(
                user_id=user.user_id,
                device_id="device-1",
                fcm_token="token-b",
                platform="ios",
            )
        )
        await DeletePushTokenCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(DeletePushTokenCommand(user_id=user.user_id, device_id="device-1"))
        profile = await CurrentUserProfileQueryUseCase(user_repository=repository).execute(
            CurrentUserProfileQuery(user_id=user.user_id)
        )
        await WithdrawalCleanupCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(WithdrawalCleanupCommand(user_id=user.user_id))

    async with postgres_session_factory() as session:
        users_count = await _count(session, orm.User)
        settings_count = await _count(session, orm.UserSettings)
        entitlement_count = await _count(session, orm.UserEntitlement)
        push_count = await _count(session, orm.UserPushToken)

    assert settings.notification_enabled is False
    assert settings.marketing_consent is True
    assert updated.push_token_id == registered.push_token_id
    assert profile.free_analysis_tokens_remaining == 3
    assert profile.notification_enabled is False
    assert profile.marketing_consent is True
    assert profile.push_token_count == 0
    assert users_count == 0
    assert settings_count == 0
    assert entitlement_count == 0
    assert push_count == 0


async def test_current_user_profile_prefers_file_content_path_over_legacy_url(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    profile_file_id = uuid4()
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user = await ResolveUserForLoginCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(
            ResolveUserForLoginCommand(
                name="프로필 이미지 우선순위",
                email="profile-priority@example.com",
                profile_image_url="https://example.com/legacy.png",
                terms_accepted=True,
                privacy_accepted=True,
            )
        )
        account_state = await repository.find_account_state(user_id=user.user_id)
        assert account_state is not None
        await repository.update_profile_image_file(
            user_id=user.user_id,
            file_id=profile_file_id,
        )
        profile = await CurrentUserProfileQueryUseCase(user_repository=repository).execute(
            CurrentUserProfileQuery(user_id=user.user_id)
        )

    assert profile.profile_image_url == f"/api/v1/files/{profile_file_id}/content"


async def test_current_user_profile_keeps_legacy_profile_image_url_without_file(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        user = await ResolveUserForLoginCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        ).execute(
            ResolveUserForLoginCommand(
                name="레거시 이미지",
                email="legacy-profile@example.com",
                profile_image_url="https://example.com/legacy.png",
                terms_accepted=True,
                privacy_accepted=True,
            )
        )
        profile = await CurrentUserProfileQueryUseCase(user_repository=repository).execute(
            CurrentUserProfileQuery(user_id=user.user_id)
        )

    assert profile.profile_image_url == "https://example.com/legacy.png"


async def test_use_cases_reject_malformed_input(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyUserRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        resolver = ResolveUserForLoginCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        )
        register_push_token = RegisterPushTokenCommandUseCase(
            user_repository=repository,
            unit_of_work=unit_of_work,
        )

        with pytest.raises(ValidationError) as invalid_email:
            await resolver.execute(
                ResolveUserForLoginCommand(
                    name="잘못된 이메일",
                    email="not-an-email",
                    profile_image_url=None,
                    terms_accepted=True,
                    privacy_accepted=True,
                )
            )
        with pytest.raises(ValidationError) as empty_device:
            await register_push_token.execute(
                RegisterPushTokenCommand(
                    user_id=UUID("00000000-0000-0000-0000-000000000001"),
                    device_id="",
                    fcm_token="token",
                    platform="android",
                )
            )
        with pytest.raises(ValidationError) as empty_token:
            await register_push_token.execute(
                RegisterPushTokenCommand(
                    user_id=UUID("00000000-0000-0000-0000-000000000001"),
                    device_id="device",
                    fcm_token="",
                    platform="android",
                )
            )

    assert [detail.field for detail in invalid_email.value.details] == ["email"]
    assert [detail.field for detail in empty_device.value.details] == ["deviceId"]
    assert [detail.field for detail in empty_token.value.details] == ["fcmToken"]


async def _count(session: AsyncSession, table: CountableUsersTable) -> int:
    count = await session.scalar(select(func.count()).select_from(table))
    if count is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return count
