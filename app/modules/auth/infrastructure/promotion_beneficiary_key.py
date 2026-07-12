import hashlib
import hmac

from app.modules.auth.application.ports.promotion_beneficiary_key_factory import (
    PromotionBeneficiaryKeyFactory,
)
from app.modules.auth.domain.value_objects import (
    Issuer,
    PromotionBeneficiaryHmacSecret,
    PromotionBeneficiaryKey,
    Subject,
)


class HmacPromotionBeneficiaryKeyFactory(PromotionBeneficiaryKeyFactory):
    def __init__(self, *, secret: PromotionBeneficiaryHmacSecret) -> None:
        self._secret = secret.value.encode("utf-8")

    def create(self, *, issuer: Issuer, subject: Subject) -> PromotionBeneficiaryKey:
        canonical_identity = f"{issuer.value}\0{subject.value}".encode()
        digest = hmac.new(self._secret, canonical_identity, hashlib.sha256).hexdigest()
        return PromotionBeneficiaryKey(f"v1:{digest}")
