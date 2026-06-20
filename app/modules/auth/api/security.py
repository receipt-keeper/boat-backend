from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.modules.auth.application.constants import (
    AUTH_SCHEME_BEARER_LOWER,
    AUTHENTICATION_REQUIRED_MESSAGE,
)
from app.modules.auth.application.principal import AuthenticatedPrincipal
from app.modules.auth.application.queries.current_principal.query import CurrentPrincipalQuery
from app.modules.auth.application.queries.current_principal.use_case import RoleAuthorizationPolicy
from app.modules.auth.dependencies import CurrentPrincipalQueryUseCaseDep
from app.modules.auth.domain.exceptions import AuthenticationError

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    query_use_case: CurrentPrincipalQueryUseCaseDep,
) -> AuthenticatedPrincipal:
    if credentials is None or credentials.scheme.lower() != AUTH_SCHEME_BEARER_LOWER:
        raise AuthenticationError(AUTHENTICATION_REQUIRED_MESSAGE)

    return await query_use_case.execute(CurrentPrincipalQuery(token=credentials.credentials))


CurrentPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def require_roles(*roles: str) -> Callable[..., AuthenticatedPrincipal]:
    def _require_role(
        principal: CurrentPrincipalDep,
    ) -> AuthenticatedPrincipal:
        RoleAuthorizationPolicy().require_roles(principal, set(roles))
        return principal

    return _require_role
