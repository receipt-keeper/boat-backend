from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RegisterPushTokenCommand:
    user_id: UUID
    device_id: str
    fcm_token: str
    platform: str
