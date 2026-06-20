from app.modules.auth.application.commands.logout.command import LogoutCommand
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.token_issuer import RefreshTokenHasher


class LogoutCommandUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        refresh_token_hasher: RefreshTokenHasher,
    ) -> None:
        self._credential_repository = credential_repository
        self._refresh_token_hasher = refresh_token_hasher

    async def execute(self, command: LogoutCommand) -> None:
        await self._credential_repository.revoke_refresh_token(
            token_hash=self._refresh_token_hasher.hash(command.refresh_token),
        )
