from app.modules.auth.application.constants import (
    AUTHENTICATION_FAILED_MESSAGE,
    AUTHORIZATION_FORBIDDEN_MESSAGE,
)
from app.modules.auth.application.ports.credential_repository import CredentialRepositoryProvider
from app.modules.auth.application.ports.token_issuer import AccessTokenVerifier
from app.modules.auth.application.principal import AuthenticatedPrincipal
from app.modules.auth.application.queries.current_principal.query import CurrentPrincipalQuery
from app.modules.auth.domain.exceptions import AuthenticationError, AuthorizationError


class CurrentPrincipalQueryUseCase:
    def __init__(
        self,
        *,
        access_token_verifier: AccessTokenVerifier,
        credential_repository_provider: CredentialRepositoryProvider,
    ) -> None:
        self._access_token_verifier = access_token_verifier
        self._credential_repository_provider = credential_repository_provider

    async def execute(self, query: CurrentPrincipalQuery) -> AuthenticatedPrincipal:
        principal = self._access_token_verifier.verify(query.token)
        credential_repository = self._credential_repository_provider.get()
        credential_exists = await credential_repository.exists_active_credential(
            user_id=principal.user_id,
            credentials_id=principal.credentials_id,
        )
        if not credential_exists:
            raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)
        return principal


class RoleAuthorizationPolicy:
    def require_roles(
        self,
        principal: AuthenticatedPrincipal,
        allowed_roles: set[str],
    ) -> None:
        if principal.role not in allowed_roles:
            raise AuthorizationError(AUTHORIZATION_FORBIDDEN_MESSAGE)
