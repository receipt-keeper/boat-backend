from typing import Final

import pytest

from app.core.config.settings import Settings
from app.core.domain.exceptions import ValidationError
from app.modules.files.infrastructure.storage.s3 import S3ObjectStorage

TEST_BUCKET: Final = "boat-test-files"
TEST_REGION: Final = "ap-northeast-2"


class _Body:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.closed = False

    def read(self) -> bytes:
        return self._content

    def close(self) -> None:
        self.closed = True


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[tuple[str, str, bytes]] = []
        self.get_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.last_body: _Body | None = None

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body
        self.put_calls.append((Bucket, Key, Body))

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        self.get_calls.append((Bucket, Key))
        body = _Body(self.objects[(Bucket, Key)])
        self.last_body = body
        return {"Body": body}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)
        self.delete_calls.append((Bucket, Key))


async def test_s3_storage_preserves_object_storage_round_trip_contract() -> None:
    client = _FakeS3Client()
    storage = S3ObjectStorage(bucket=TEST_BUCKET, region=TEST_REGION, client=client)

    stored = await storage.put(key="users/user/files/file/original", content=b"receipt")
    content = await storage.read(key=stored.storage_key)
    await storage.delete(key=stored.storage_key)

    assert stored.storage_key == "users/user/files/file/original"
    assert stored.size == len(b"receipt")
    assert stored.checksum == "6f32860910ca0fb2a20c7fda143666b09dbf8db5238195c90a586fb542ff0cad"
    assert content == b"receipt"
    assert client.put_calls == [(TEST_BUCKET, stored.storage_key, b"receipt")]
    assert client.get_calls == [(TEST_BUCKET, stored.storage_key)]
    assert client.delete_calls == [(TEST_BUCKET, stored.storage_key)]
    assert client.last_body is not None
    assert client.last_body.closed is True
    assert client.objects == {}


async def test_s3_storage_rejects_invalid_storage_key_before_sdk_call() -> None:
    client = _FakeS3Client()
    storage = S3ObjectStorage(bucket=TEST_BUCKET, region=TEST_REGION, client=client)

    with pytest.raises(ValidationError):
        await storage.put(key="../escape", content=b"blocked")

    assert client.put_calls == []


def test_s3_settings_require_bucket_and_region() -> None:
    with pytest.raises(
        ValueError,
        match="FILE_STORAGE_BACKEND=s3 requires S3_BUCKET and S3_REGION",
    ):
        Settings(file_storage_backend="s3")


def test_s3_settings_require_static_credentials_as_a_pair() -> None:
    with pytest.raises(
        ValueError,
        match="S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be configured together",
    ):
        Settings(
            file_storage_backend="s3",
            s3_bucket=TEST_BUCKET,
            s3_region=TEST_REGION,
            s3_access_key_id="access-key",
        )
