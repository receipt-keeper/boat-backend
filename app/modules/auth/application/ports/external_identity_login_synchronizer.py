from abc import ABC, abstractmethod

from app.modules.auth.domain.model import ExternalIdentity


class ExternalIdentityLoginSynchronizer(ABC):
    @abstractmethod
    async def synchronize(self, *, identity: ExternalIdentity) -> None:
        raise NotImplementedError
