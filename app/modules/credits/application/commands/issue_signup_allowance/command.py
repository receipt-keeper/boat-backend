from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

SIGNUP_ALLOWANCE_IDEMPOTENCY_PREFIX: Final = "signup-allowance:"


def signup_allowance_idempotency_key(handle: str) -> str:
    return f"{SIGNUP_ALLOWANCE_IDEMPOTENCY_PREFIX}{handle}"


@dataclass(frozen=True, slots=True)
class IssueSignupAllowanceCommand:
    user_id: UUID
    subject_handle: str
    # 현재 발급에 쓰이는 subject_handle을 포함해, 키 회전으로 은퇴한 이전 버전
    # handle까지 모두 담는다. 조회(중복 판정)는 이 목록 전부를 대상으로 하고,
    # 신규 발급은 항상 subject_handle(현행 버전)로만 이뤄진다. handle 계산은
    # auth가 소유하므로 credits는 계산된 문자열만 받는다.
    candidate_handles: Sequence[str]
