from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GrantCreditCommandResult:
    total_granted_count: int
    remaining_count: int
