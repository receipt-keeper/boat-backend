from app.modules.auth.infrastructure.persistence.withdrawn_identity_purger import (
    WithdrawnIdentityPurger,
)

__all__ = ("build_withdrawn_identity_purger",)


def build_withdrawn_identity_purger() -> WithdrawnIdentityPurger:
    return WithdrawnIdentityPurger()
