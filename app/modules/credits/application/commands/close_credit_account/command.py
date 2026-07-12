from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CloseCreditsAccountCommand:
    user_id: UUID
    # 신원 조회에 쓸 수 있는 전 버전 handle 목록(현행 handle 포함). 신원을 확인할 수
    # 없는 엣지(예: 연결된 external identity가 없음)면 빈 목록을 전달한다 - 이 경우
    # 전량 삭제로 폴백한다(가입 보너스 claim 보존 없이 기존 DeleteUserCredits와 동일 동작).
    candidate_handles: Sequence[str]
