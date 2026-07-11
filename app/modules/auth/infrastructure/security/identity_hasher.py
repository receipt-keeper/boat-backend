import hashlib
import hmac

from app.modules.auth.application.ports.withdrawn_identity import IdentityHasher


class HmacIdentityHasher(IdentityHasher):
    def __init__(self, *, secret: str) -> None:
        self._secret = secret

    def hash(self, *, issuer: str, subject: str) -> str:
        message = f"{issuer}:{subject}".encode()
        return hmac.new(self._secret.encode(), message, hashlib.sha256).hexdigest()
