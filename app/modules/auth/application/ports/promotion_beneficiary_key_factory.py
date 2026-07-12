from typing import Protocol

from app.modules.auth.domain.value_objects import (
    Issuer,
    PromotionBeneficiaryKey,
    Subject,
)


class PromotionBeneficiaryKeyFactory(Protocol):
    def create(self, *, issuer: Issuer, subject: Subject) -> PromotionBeneficiaryKey: ...
