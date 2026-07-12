from dataclasses import dataclass

from app.modules.auth.application.commands.login.use_case import LoginCommandUseCase
from app.modules.auth.application.commands.logout.use_case import LogoutCommandUseCase
from app.modules.auth.application.commands.refresh.use_case import RefreshTokenCommandUseCase
from app.modules.auth.application.ports.external_identity_login_synchronizer import (
    ExternalIdentityLoginSynchronizer,
)
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.domain.value_objects import PromotionBeneficiaryHmacSecret
from app.modules.auth.infrastructure.promotion_beneficiary_key import (
    HmacPromotionBeneficiaryKeyFactory,
)
from app.modules.auth.infrastructure.tokens.jwt import JwtAccessTokenService
from app.modules.auth.infrastructure.tokens.opaque_refresh_token import OpaqueRefreshTokenIssuer
from app.modules.auth.tests.credential_repository_fake import FakeCredentialRepository
from tests.support.unit_of_work import FakeUnitOfWork

TEST_SIGNING_KEY = "x" * 48
TEST_PROMOTION_BENEFICIARY_HMAC_SECRET = "b" * 48


@dataclass(slots=True)
class FakeExternalIdentityVerifier(ExternalIdentityVerifier):
    identity: ExternalIdentity | None = None
    error: Exception | None = None

    async def verify(self, provider_token: str) -> ExternalIdentity:
        if self.error is not None:
            raise self.error
        if self.identity is None:
            raise AssertionError("identity or error is required")
        return self.identity


class NoOpExternalIdentityLoginSynchronizer(ExternalIdentityLoginSynchronizer):
    async def synchronize(self, *, identity: ExternalIdentity) -> None:
        assert identity.issuer.value
        assert identity.subject.value


def build_access_token_issuer() -> JwtAccessTokenService:
    return JwtAccessTokenService(
        secret_key=TEST_SIGNING_KEY,
        issuer="boat-backend-test",
        audience="boat-api-test",
        expires_minutes=30,
    )


def build_refresh_token_service() -> OpaqueRefreshTokenIssuer:
    return OpaqueRefreshTokenIssuer(
        pepper="test-pepper",
        expires_days=14,
    )


def build_promotion_beneficiary_key_factory() -> HmacPromotionBeneficiaryKeyFactory:
    return HmacPromotionBeneficiaryKeyFactory(
        secret=PromotionBeneficiaryHmacSecret(TEST_PROMOTION_BENEFICIARY_HMAC_SECRET)
    )


def build_login_command_use_case(
    *,
    verifier: FakeExternalIdentityVerifier,
    repository: FakeCredentialRepository,
) -> LoginCommandUseCase:
    refresh_token_service = build_refresh_token_service()
    return LoginCommandUseCase(
        identity_verifier=verifier,
        login_synchronizer=NoOpExternalIdentityLoginSynchronizer(),
        credential_repository=repository,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=refresh_token_service,
        unit_of_work=FakeUnitOfWork(),
    )


def build_refresh_command_use_case(
    *,
    repository: FakeCredentialRepository,
) -> RefreshTokenCommandUseCase:
    refresh_token_service = build_refresh_token_service()
    return RefreshTokenCommandUseCase(
        credential_repository=repository,
        access_token_issuer=build_access_token_issuer(),
        refresh_token_issuer=refresh_token_service,
        refresh_token_hasher=refresh_token_service,
        unit_of_work=FakeUnitOfWork(),
    )


def build_logout_command_use_case(*, repository: FakeCredentialRepository) -> LogoutCommandUseCase:
    refresh_token_service = build_refresh_token_service()
    return LogoutCommandUseCase(
        credential_repository=repository,
        refresh_token_hasher=refresh_token_service,
        unit_of_work=FakeUnitOfWork(),
    )
