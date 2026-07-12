from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.auth.domain.model import ExternalIdentity


class SignupPromotionRedeemer(ABC):
    @abstractmethod
    async def redeem(self, *, identity: ExternalIdentity, user_id: UUID) -> None:
        raise NotImplementedError
