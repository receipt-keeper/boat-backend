from app.modules.auth.application.constants import AUTH_SCHEME_BEARER
from app.modules.auth.application.ports.credential_repository import CredentialRepository
from app.modules.auth.application.ports.token_issuer import (
    AccessTokenIssuer,
    RefreshTokenHasher,
    RefreshTokenIssuer,
)
from app.modules.auth.application.refresh.schemas import RefreshTokenCommand, RefreshTokenResult


class RefreshTokenUseCase:
    def __init__(
        self,
        *,
        credential_repository: CredentialRepository,
        access_token_issuer: AccessTokenIssuer,
        refresh_token_issuer: RefreshTokenIssuer,
        refresh_token_hasher: RefreshTokenHasher,
    ) -> None:
        self._credential_repository = credential_repository
        self._access_token_issuer = access_token_issuer
        self._refresh_token_issuer = refresh_token_issuer
        self._refresh_token_hasher = refresh_token_hasher

    async def execute(self, command: RefreshTokenCommand) -> RefreshTokenResult:
        rotated_refresh_token = self._refresh_token_issuer.issue()
        credentials = await self._credential_repository.rotate_refresh_token(
            token_hash=self._refresh_token_hasher.hash(command.refresh_token),
            new_token_hash=rotated_refresh_token.token_hash,
            expires_at=rotated_refresh_token.expires_at,
        )
        access_token = self._access_token_issuer.issue(
            user_id=credentials.user_id,
            credentials_id=credentials.credentials_id,
            role=credentials.role.value,
        )

        return RefreshTokenResult(
            access_token=access_token.token,
            refresh_token=rotated_refresh_token.token,
            token_type=AUTH_SCHEME_BEARER,
            expires_in=access_token.expires_in,
        )
