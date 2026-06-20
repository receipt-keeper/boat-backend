from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProvisionedUser:
    user_id: UUID


@dataclass(frozen=True, slots=True)
class UserProvisioningRequest:
    name: str | None
    email: str | None
    normalized_email: str
    profile_image_url: str | None
    terms_version: str | None
    privacy_version: str | None
    terms_accepted: bool
    privacy_accepted: bool
    marketing_consent: bool


class UserProvisioner(ABC):
    @abstractmethod
    async def provision(self, *, request: UserProvisioningRequest) -> ProvisionedUser:
        raise NotImplementedError
