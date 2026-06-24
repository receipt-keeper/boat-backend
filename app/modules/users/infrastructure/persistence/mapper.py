from app.modules.users.domain.model import (
    User as DomainUser,
)
from app.modules.users.domain.model import (
    UserEntitlement as DomainUserEntitlement,
)
from app.modules.users.domain.model import (
    UserPushToken as DomainUserPushToken,
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
        profile_image_file_id=record.profile_image_file_id,
    )


def user_to_record(user: DomainUser) -> orm.User:
    return orm.User(
        id=user.id,
        name=user.name,
        nickname=user.nickname,
        email=None if user.email is None else user.email.value,
        profile_image_url=user.profile_image_url,
        profile_image_file_id=user.profile_image_file_id,
    )


def settings_to_domain(record: orm.UserSettings) -> DomainUserSettings:
    return DomainUserSettings.create(
        user_id=record.user_id,
        notification_enabled=record.notification_enabled,
        marketing_consent=record.marketing_consent,
        terms_version=record.terms_version,
        privacy_version=record.privacy_version,
        terms_accepted_at=record.terms_accepted_at,
        privacy_accepted_at=record.privacy_accepted_at,
        marketing_consent_updated_at=record.marketing_consent_updated_at,
    )


def settings_to_record(settings: DomainUserSettings) -> orm.UserSettings:
    return orm.UserSettings(
        user_id=settings.id,
        notification_enabled=settings.notification_enabled,
        marketing_consent=settings.marketing_consent,
        terms_version=settings.terms_version,
        privacy_version=settings.privacy_version,
        terms_accepted_at=settings.terms_accepted_at,
        privacy_accepted_at=settings.privacy_accepted_at,
        marketing_consent_updated_at=settings.marketing_consent_updated_at,
    )


def entitlement_to_domain(record: orm.UserEntitlement) -> DomainUserEntitlement:
    return DomainUserEntitlement.create(
        user_id=record.user_id,
        free_analysis_tokens_remaining=record.free_analysis_tokens_remaining,
    )


def entitlement_to_record(entitlement: DomainUserEntitlement) -> orm.UserEntitlement:
    return orm.UserEntitlement(
        user_id=entitlement.id,
        free_analysis_tokens_remaining=entitlement.free_analysis_tokens_remaining.value,
    )


def push_token_to_domain(record: orm.UserPushToken) -> DomainUserPushToken:
    return DomainUserPushToken.create(
        push_token_id=record.id,
        user_id=record.user_id,
        device_id=record.device_id,
        fcm_token=record.fcm_token,
        platform=record.platform,
    )


def push_token_to_record(push_token: DomainUserPushToken) -> orm.UserPushToken:
    return orm.UserPushToken(
        id=push_token.id,
        user_id=push_token.user_id,
        device_id=push_token.device_id,
        fcm_token=push_token.fcm_token,
        platform=push_token.platform.value,
    )
