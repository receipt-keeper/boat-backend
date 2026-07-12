import hashlib
import hmac
from collections.abc import Mapping, Sequence

from app.modules.auth.application.ports.benefit_subject_handle import (
    BenefitSubjectHandleProvider,
)


class HmacBenefitSubjectHandleProvider(BenefitSubjectHandleProvider):
    """HMAC-SHA256 + 키 링 기반 benefit subject handle 제공자.

    입력은 (namespace, subject=firebase uid) 쌍뿐이다 - issuer(google/apple)는
    입력에서 제외해, 동일 Firebase 유저가 로그인 수단을 바꿔도 같은 handle이 나온다.
    handle 문자열 포맷은 "{version}:{64hex}"이며, 버전 프리픽스가 키 회전을 지원한다.
    발급(신규 grant)은 항상 현행 버전 키만 쓰고, 중복 판정(조회)은 현행 + 은퇴 전
    버전 키로 계산한 handle을 모두 후보로 내놓는다.
    """

    def __init__(
        self,
        *,
        namespace: str,
        current_version: str,
        current_secret: str,
        retired_secrets: Mapping[str, str] | None = None,
    ) -> None:
        self._namespace = namespace
        self._current_version = current_version
        self._current_secret = current_secret
        self._retired_secrets = dict(retired_secrets) if retired_secrets else {}

    def handle(self, *, subject: str) -> str:
        return self._versioned_handle(
            version=self._current_version,
            secret=self._current_secret,
            subject=subject,
        )

    def candidate_handles(self, *, subject: str) -> Sequence[str]:
        handles = [self.handle(subject=subject)]
        handles.extend(
            self._versioned_handle(version=version, secret=secret, subject=subject)
            for version, secret in self._retired_secrets.items()
        )
        return handles

    def _versioned_handle(self, *, version: str, secret: str, subject: str) -> str:
        # 길이 프리픽스 인코딩으로 서로 다른 (namespace, subject) 쌍이 같은
        # 메시지 바이트열이 되는 구분자 충돌을 원천 차단한다.
        message = _length_prefixed(self._namespace) + _length_prefixed(subject)
        digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        return f"{version}:{digest}"


def _length_prefixed(value: str) -> bytes:
    data = value.encode()
    return len(data).to_bytes(4, "big") + data
