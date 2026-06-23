from uuid import UUID

from app.modules.auth.domain.model import (
    AuthSession as DomainAuthSession,
)
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


def user_credential_to_record(credentials: DomainUserCredential) -> orm.UserCredential:
    return orm.UserCredential(
        id=credentials.credentials_id,
        user_id=credentials.user_id,
        role=credentials.role.value,
        last_login_at=credentials.last_login_at,
    )


def external_identity_to_record(
    identity: DomainExternalIdentity,
    *,
    credentials_id: UUID,
) -> orm.ExternalIdentity:
    return orm.ExternalIdentity(
        id=identity.id,
        credentials_id=credentials_id,
        issuer=identity.issuer.value,
        subject=identity.subject.value,
        provider=identity.provider.value,
        email=None if identity.email is None else identity.email.value,
        normalized_email=_canonical_email(identity),
        email_verified=identity.email_verified,
    )


def auth_session_to_record(session: DomainAuthSession) -> orm.AuthSession:
    return orm.AuthSession(
        id=session.session_id,
        credentials_id=session.credentials_id,
        revoked_at=session.revoked_at,
    )


def refresh_token_to_record(token: DomainRefreshToken) -> orm.RefreshToken:
    return orm.RefreshToken(
        id=token.id,
        credentials_id=token.credentials_id,
        session_id=token.session_id,
        token_hash=token.token_hash.value,
        expires_at=token.expires_at,
    )


def _canonical_email(identity: DomainExternalIdentity) -> str | None:
    if identity.email is None:
        return None
    return identity.email.value.lower()
