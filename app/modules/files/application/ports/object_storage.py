from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    storage_backend: str
    storage_key: str
    size: int
    checksum: str


class ObjectStorage(Protocol):
    async def put(self, *, key: str, content: bytes) -> StoredObject:
        raise NotImplementedError

    async def read(self, *, key: str) -> bytes:
        raise NotImplementedError

    async def delete(self, *, key: str) -> None:
        raise NotImplementedError
