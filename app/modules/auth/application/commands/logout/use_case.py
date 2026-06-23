from app.core.application.unit_of_work import UnitOfWork
from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.token_issuer import RefreshTokenHasher


class LogoutCommandUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        refresh_token_hasher: RefreshTokenHasher,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credential_repository = credential_repository
        self._refresh_token_hasher = refresh_token_hasher
        self._unit_of_work = unit_of_work

    async def execute(self, command: LogoutCommand) -> None:
        await self._credential_repository.revoke_session_by_refresh_token(
            token_hash=self._refresh_token_hasher.hash(command.refresh_token),
        )
        await self._unit_of_work.commit()
