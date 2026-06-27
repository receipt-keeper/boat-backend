from app.modules.users.domain.model import (
    User as DomainUser,
)
from app.modules.users.domain.model import (
    UserSettings as DomainUserSettings,
)
from app.modules.users.infrastructure.persistence import orm


def user_to_domain(record: orm.User) -> DomainUser:
    return DomainUser.create(
        user_id=record.id,
        name=record.name,
        email=record.email,
        nickname=record.nickname,
        profile_image_url=record.profile_image_url,
    )


def user_to_record(user: DomainUser) -> orm.User:
    return orm.User(
        id=user.id,
        name=user.name,
        nickname=user.nickname,
        email=None if user.email is None else user.email.value,
        profile_image_url=user.profile_image_url,
    )


def settings_to_domain(record: orm.UserSettings) -> DomainUserSettings:
    return DomainUserSettings.create(
        user_id=record.user_id,
        terms_version=record.terms_version,
        privacy_version=record.privacy_version,
        terms_accepted_at=record.terms_accepted_at,
        privacy_accepted_at=record.privacy_accepted_at,
    )


def settings_to_record(settings: DomainUserSettings) -> orm.UserSettings:
    return orm.UserSettings(
        user_id=settings.id,
        terms_version=settings.terms_version,
        privacy_version=settings.privacy_version,
        terms_accepted_at=settings.terms_accepted_at,
        privacy_accepted_at=settings.privacy_accepted_at,
    )
