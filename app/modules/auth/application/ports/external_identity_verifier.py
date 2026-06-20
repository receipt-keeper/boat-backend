from abc import ABC, abstractmethod

from app.modules.auth.domain.model import ExternalIdentity


class ExternalIdentityVerifier(ABC):
    @abstractmethod
    async def verify(self, provider_token: str) -> ExternalIdentity:
        raise NotImplementedError
