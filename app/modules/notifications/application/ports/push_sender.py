from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.modules.notifications.domain.model import UserPushToken


@dataclass(frozen=True, slots=True)
class PushMessage:
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PushSendReport:
    invalid_tokens: tuple[str, ...] = ()


class PushSender(ABC):
    @abstractmethod
    async def send(
        self,
        *,
        tokens: Sequence[UserPushToken],
        message: PushMessage,
    ) -> PushSendReport:
        raise NotImplementedError
