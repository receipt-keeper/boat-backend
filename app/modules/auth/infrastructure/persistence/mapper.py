from app.modules.auth.domain.model import (
    ExternalIdentity as DomainExternalIdentity,
)
from app.modules.auth.domain.model import (
    RefreshToken as DomainRefreshToken,
)
from app.modules.auth.domain.model import (
    UserCredential as DomainUserCredential,
)
from app.modules.auth.infrastructure.persistence import orm


def user_credential_to_domain(record: orm.UserCredential) -> DomainUserCredential:
    return DomainUserCredential.create(
        credentials_id=record.id,
        user_id=record.user_id,
        role=record.role,
        last_login_at=record.last_login_at,
    )


def external_identity_to_record(
    identity: DomainExternalIdentity,
    *,
    credentials_id,
) -> orm.ExternalIdentity:
    return orm.ExternalIdentity(
        id=identity.id,
        credentials_id=credentials_id,
        issuer=identity.issuer.value,
        subject=identity.subject.value,
        provider=identity.provider.value,
    )


def refresh_token_to_record(token: DomainRefreshToken) -> orm.RefreshToken:
    return orm.RefreshToken(
        id=token.id,
        credentials_id=token.credentials_id,
        token_hash=token.token_hash.value,
        expires_at=token.expires_at,
    )
