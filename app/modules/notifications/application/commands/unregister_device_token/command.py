from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UnregisterDeviceTokenCommand:
    user_id: UUID
    device_id: str
