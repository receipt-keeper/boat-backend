from dataclasses import dataclass
from enum import StrEnum


class SignupAllowanceOutcome(StrEnum):
    ISSUED = "issued"
    REACTIVATED = "reactivated"


@dataclass(frozen=True, slots=True)
class IssueSignupAllowanceCommandResult:
    outcome: SignupAllowanceOutcome
    total_granted_count: int
    remaining_count: int
