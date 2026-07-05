from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain.value_objects import DevicePlatform


@dataclass(frozen=True, slots=True)
class RegisterDeviceTokenCommand:
    user_id: UUID
    token: str
    platform: DevicePlatform
