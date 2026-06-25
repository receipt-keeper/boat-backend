from abc import ABC, abstractmethod
from uuid import UUID


class ProfileImageFileValidator(ABC):
    @abstractmethod
    async def ensure_owned_image_file(self, *, user_id: UUID, file_id: UUID) -> None:
        raise NotImplementedError
