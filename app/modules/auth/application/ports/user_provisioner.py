from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProvisionedUser:
    user_id: UUID


class UserProvisioner(ABC):
    @abstractmethod
    async def provision(self, *, name: str | None, email: str | None) -> ProvisionedUser:
        raise NotImplementedError
