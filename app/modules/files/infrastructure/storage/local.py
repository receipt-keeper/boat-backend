import hashlib
import os
from pathlib import Path

from anyio.to_thread import run_sync

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.files.application.ports.object_storage import StoredObject
from app.modules.files.domain.value_objects import StorageKey


class LocalObjectStorage:
    def __init__(self, *, root: str) -> None:
        self._root = Path(root)

    async def put(self, *, key: str, content: bytes) -> StoredObject:
        await run_sync(self._write_bytes, key, content)
        return StoredObject(
            storage_key=key,
            size=len(content),
            checksum=hashlib.sha256(content, usedforsecurity=False).hexdigest(),
        )

    async def read(self, *, key: str) -> bytes:
        return await run_sync(self._read_bytes, key)

    async def delete(self, *, key: str) -> None:
        await run_sync(self._delete_file, key)

    def _target_path(self, key: str) -> Path:
        StorageKey(key)
        root = self._root.resolve(strict=False)
        target = (root / Path(key)).resolve(strict=False)
        if not target.is_relative_to(root):
            raise ValidationError(
                [ErrorDetail(field="storageKey", message="파일 저장 키가 올바르지 않습니다.")]
            )
        return target

    def _write_bytes(self, key: str, content: bytes) -> None:
        target = self._target_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(content)
        os.replace(temporary, target)

    def _read_bytes(self, key: str) -> bytes:
        return self._target_path(key).read_bytes()

    def _delete_file(self, key: str) -> None:
        target = self._target_path(key)
        try:
            target.unlink()
        except FileNotFoundError:
            return
