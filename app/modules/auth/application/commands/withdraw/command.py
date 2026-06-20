from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class WithdrawAccountCommand:
    user_id: UUID
    credentials_id: UUID
