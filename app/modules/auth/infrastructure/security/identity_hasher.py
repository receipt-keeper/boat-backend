import hashlib
import hmac

from app.modules.auth.application.ports.withdrawn_identity import IdentityHasher


class HmacIdentityHasher(IdentityHasher):
    def __init__(self, *, secret: str) -> None:
        self._secret = secret

    def hash(self, *, issuer: str, subject: str) -> str:
        # 길이 프리픽스 인코딩으로 서로 다른 (issuer, subject) 쌍이 같은
        # 메시지 바이트열이 되는 구분자 충돌을 원천 차단한다.
        # 이 포맷은 저장된 tombstone 해시와의 호환 계약이므로 변경하면 안 된다.
        message = _length_prefixed(issuer) + _length_prefixed(subject)
        return hmac.new(self._secret.encode(), message, hashlib.sha256).hexdigest()


def _length_prefixed(value: str) -> bytes:
    data = value.encode()
    return len(data).to_bytes(4, "big") + data
