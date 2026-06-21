from typing import Annotated, Final

from fastapi import Depends, HTTPException, Request, status

from app.core.security.principal import AuthenticatedPrincipal

_CURRENT_PRINCIPAL_STATE_KEY: Final = "current_principal"


def set_current_principal(request: Request, principal: AuthenticatedPrincipal) -> None:
    setattr(request.state, _CURRENT_PRINCIPAL_STATE_KEY, principal)


async def get_current_principal(request: Request) -> AuthenticatedPrincipal:
    principal = getattr(request.state, _CURRENT_PRINCIPAL_STATE_KEY, None)
    if isinstance(principal, AuthenticatedPrincipal):
        return principal
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 필요합니다.",
    )


CurrentPrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
