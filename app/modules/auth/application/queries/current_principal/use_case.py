from app.core.security.principal import AuthenticatedPrincipal
from app.modules.auth.application.ports.credential_repository import ActiveSessionChecker
from app.modules.auth.application.ports.token_issuer import AccessTokenVerifier
from app.modules.auth.application.queries.current_principal.query import CurrentPrincipalQuery
from app.modules.auth.domain.exceptions import AuthenticationError, AuthorizationError


class CurrentPrincipalQueryUseCase:
    def __init__(
        self,
        *,
        access_token_verifier: AccessTokenVerifier,
        active_session_checker: ActiveSessionChecker,
    ) -> None:
        self._access_token_verifier = access_token_verifier
        self._active_session_checker = active_session_checker

    async def execute(self, query: CurrentPrincipalQuery) -> AuthenticatedPrincipal:
        principal = self._access_token_verifier.verify(query.token)
        session_exists = await self._active_session_checker.exists_active_session(
            user_id=principal.user_id,
            credentials_id=principal.credentials_id,
            session_id=principal.session_id,
        )
        if not session_exists:
            raise AuthenticationError()
        return principal


class RoleAuthorizationPolicy:
    def require_roles(
        self,
        principal: AuthenticatedPrincipal,
        allowed_roles: set[str],
    ) -> None:
        if principal.role not in allowed_roles:
            raise AuthorizationError()
