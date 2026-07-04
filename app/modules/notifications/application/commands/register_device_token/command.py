from dataclasses import dataclass
from uuid import UUID

from app.modules.notifications.domain.value_objects import DevicePlatform


@dataclass(frozen=True, slots=True)
class RegisterDeviceTokenCommand:
    user_id: UUID
    device_id: str
    fcm_token: str
    platform: DevicePlatform
