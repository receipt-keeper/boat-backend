from dataclasses import dataclass
from uuid import UUID

from app.core.domain.entity import Entity


@dataclass(eq=False)
class ExampleUser(Entity[UUID]):
    nickname: str
    email: str
