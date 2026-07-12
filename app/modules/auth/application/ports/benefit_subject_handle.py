from abc import ABC, abstractmethod
from collections.abc import Sequence


class BenefitSubjectHandleProvider(ABC):
    """가입 보너스 claim 판정에 쓰이는 benefit subject handle을 계산하는 포트.

    입력은 Firebase 신원의 uid(issuer/provider와 무관)뿐이다 - 동일 Firebase 유저가
    로그인 수단(google/apple)을 바꿔도 같은 handle이 나오게 한다. handle 계산은
    auth가 소유하고, credits는 계산된 문자열만 받는다.
    """

    @abstractmethod
    def handle(self, *, subject: str) -> str:
        """현행 키 버전으로 계산한 handle을 반환한다(신규 발급에 사용)."""
        raise NotImplementedError

    @abstractmethod
    def candidate_handles(self, *, subject: str) -> Sequence[str]:
        """현행 + 은퇴 전 버전 키로 계산한 handle 목록을 반환한다(현행 우선).

        키 회전 중 중복 판정(조회)에 쓰인다.
        """
        raise NotImplementedError
