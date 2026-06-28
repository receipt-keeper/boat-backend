from uuid import UUID

from fastapi import Request

from app.core.db.session import request_async_session
from app.modules.auth.application.ports.credential_repository import ActiveSessionChecker
from app.modules.auth.application.ports.user_provisioner import (
    ProvisionedUser,
    UserProvisioner,
    UserProvisioningRequest,
)
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.users.application.commands.resolve_user_for_login.command import (
    ResolveUserForLoginCommand,
)
from app.modules.users.application.commands.resolve_user_for_login.use_case import (
    ResolveUserForLoginCommandUseCase,
)


class ProvisionUserPortAdapter(UserProvisioner):
    def __init__(
        self,
        command_use_case: ResolveUserForLoginCommandUseCase,
        *,
        default_profile_image_url: str | None = None,
    ) -> None:
        self._command_use_case = command_use_case
        self._default_profile_image_url = default_profile_image_url

    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        result = await self._command_use_case.execute(
            ResolveUserForLoginCommand(
                name=request.name,
                email=request.email,
                profile_image_url=request.profile_image_url or self._default_profile_image_url,
                terms_version=request.terms_version,
                privacy_version=request.privacy_version,
                terms_accepted=request.terms_accepted,
                privacy_accepted=request.privacy_accepted,
            )
        )
        return ProvisionedUser(user_id=result.user_id)


class RequestActiveSessionChecker(ActiveSessionChecker):
    def __init__(self, request: Request) -> None:
        self._request = request

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        async with request_async_session(self._request) as session:
            return await SqlAlchemyCredentialRepository(session).exists_active_session(
                user_id=user_id,
                credentials_id=credentials_id,
                session_id=session_id,
            )
