from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.modules.auth.application.queries.current_principal.query import CurrentPrincipalQuery
from app.modules.auth.application.queries.current_principal.use_case import RoleAuthorizationPolicy
from app.modules.auth.dependencies import CurrentPrincipalQueryUseCaseDep
from app.modules.auth.domain.exceptions import AuthenticationRequiredError

_bearer_scheme = HTTPBearer(auto_error=False)


async def authenticate_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    query_use_case: CurrentPrincipalQueryUseCaseDep,
) -> AuthenticatedPrincipal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise AuthenticationRequiredError()

    principal = await query_use_case.execute(CurrentPrincipalQuery(token=credentials.credentials))
    set_current_principal(request, principal)
    return principal


CurrentPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(authenticate_current_principal)]


def require_roles(*roles: str) -> Callable[..., AuthenticatedPrincipal]:
    def _require_role(
        principal: CurrentPrincipalDep,
    ) -> AuthenticatedPrincipal:
        RoleAuthorizationPolicy().require_roles(principal, set(roles))
        return principal

    return _require_role
