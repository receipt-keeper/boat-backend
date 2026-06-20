from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeletePushTokenCommand:
    user_id: UUID
    device_id: str
