from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Final, Protocol, runtime_checkable

from anyio.to_thread import run_sync
from boto3.session import Session
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config.settings import Settings
from app.core.domain.exceptions import ErrorDetail, ExternalServiceError, ValidationError
from app.modules.files.application.ports.object_storage import StoredObject
from app.modules.files.domain.value_objects import StorageKey

_PUT_OBJECT_METHOD: Final = "put_object"
_GET_OBJECT_METHOD: Final = "get_object"
_DELETE_OBJECT_METHOD: Final = "delete_object"


@runtime_checkable
class _ReadableBody(Protocol):
    def read(self) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _S3Client(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        raise NotImplementedError

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, _ReadableBody]:
        raise NotImplementedError

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        raise NotImplementedError


class _BotoS3ClientAdapter:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        getattr(self._client, _PUT_OBJECT_METHOD)(Bucket=Bucket, Key=Key, Body=Body)

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, _ReadableBody]:
        response = getattr(self._client, _GET_OBJECT_METHOD)(Bucket=Bucket, Key=Key)
        if not isinstance(response, Mapping):
            raise ExternalServiceError("S3 응답 형식이 올바르지 않습니다.")
        body = response.get("Body")
        if not isinstance(body, _ReadableBody):
            raise ExternalServiceError("S3 응답에 파일 본문이 없습니다.")
        return {"Body": body}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        getattr(self._client, _DELETE_OBJECT_METHOD)(Bucket=Bucket, Key=Key)


class S3ObjectStorage:
    def __init__(self, *, bucket: str, region: str, client: _S3Client) -> None:
        self._bucket = bucket
        self._region = region
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ObjectStorage:
        if settings.s3_bucket is None or settings.s3_region is None:
            raise ValueError("FILE_STORAGE_BACKEND=s3 requires S3_BUCKET and S3_REGION")

        session = Session()
        if settings.s3_access_key_id and settings.s3_secret_access_key:
            client = _BotoS3ClientAdapter(
                session.client(
                    "s3",
                    region_name=settings.s3_region,
                    endpoint_url=settings.s3_endpoint_url,
                    aws_access_key_id=settings.s3_access_key_id,
                    aws_secret_access_key=settings.s3_secret_access_key,
                )
            )
        else:
            client = _BotoS3ClientAdapter(
                session.client(
                    "s3",
                    region_name=settings.s3_region,
                    endpoint_url=settings.s3_endpoint_url,
                )
            )
        return cls(bucket=settings.s3_bucket, region=settings.s3_region, client=client)

    async def put(self, *, key: str, content: bytes) -> StoredObject:
        _validate_storage_key(key)
        try:
            await run_sync(self._put_object, key, content)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError("파일 저장소에 업로드하지 못했습니다.") from exc
        return StoredObject(
            storage_key=key,
            size=len(content),
            checksum=hashlib.sha256(content, usedforsecurity=False).hexdigest(),
        )

    async def read(self, *, key: str) -> bytes:
        _validate_storage_key(key)
        try:
            return await run_sync(self._read_object, key)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError("파일 저장소에서 파일을 읽지 못했습니다.") from exc

    async def delete(self, *, key: str) -> None:
        _validate_storage_key(key)
        try:
            await run_sync(self._delete_object, key)
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError("파일 저장소에서 파일을 삭제하지 못했습니다.") from exc

    def _put_object(self, key: str, content: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content)

    def _read_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def _delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


def _validate_storage_key(key: str) -> None:
    try:
        StorageKey(key)
    except ValidationError:
        raise ValidationError(
            [ErrorDetail(field="storageKey", message="파일 저장 키가 올바르지 않습니다.")]
        ) from None
