from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.modules.auth.application.constants import (
    AUTH_SCHEME_BEARER_LOWER,
    AUTHENTICATION_REQUIRED_MESSAGE,
)
from app.modules.auth.application.principal import AuthenticatedPrincipal
from app.modules.auth.dependencies import AuthorizeUseCaseDep
from app.modules.auth.domain.exceptions import AuthenticationError

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    use_case: AuthorizeUseCaseDep,
) -> AuthenticatedPrincipal:
    if credentials is None or credentials.scheme.lower() != AUTH_SCHEME_BEARER_LOWER:
        raise AuthenticationError(AUTHENTICATION_REQUIRED_MESSAGE)

    return await use_case.current_principal(credentials.credentials)


CurrentPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def require_roles(*roles: str) -> Callable[..., AuthenticatedPrincipal]:
    def _require_role(
        principal: CurrentPrincipalDep,
        use_case: AuthorizeUseCaseDep,
    ) -> AuthenticatedPrincipal:
        use_case.require_roles(principal, set(roles))
        return principal

    return _require_role
