from app.modules.credits.infrastructure.persistence.claim_purger import CreditClaimPurger

__all__ = ("build_credit_claim_purger",)


def build_credit_claim_purger() -> CreditClaimPurger:
    return CreditClaimPurger()
