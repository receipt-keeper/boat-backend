from abc import ABC, abstractmethod
from collections.abc import Sequence


class IdentityHasher(ABC):
    @abstractmethod
    def hash(self, *, issuer: str, subject: str) -> str:
        raise NotImplementedError


class WithdrawnIdentityRegistry(ABC):
    @abstractmethod
    async def mark_withdrawn(self, *, identity_hashes: Sequence[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, *, identity_hash: str) -> bool:
        raise NotImplementedError
