import asyncio
from dataclasses import dataclass
from typing import Any

import boto3

from packages.config import get_settings


class ObjectStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadTicket:
    url: str
    required_headers: dict[str, str]
    expires_in_seconds: int


class ObjectStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.object_store_bucket
        self.endpoint = settings.object_store_endpoint
        self.region = settings.object_store_region
        self.access_key = settings.object_store_access_key
        self.secret_key = settings.object_store_secret_key

    def _client(self) -> Any:
        if not self.endpoint or not self.access_key or not self.secret_key:
            raise ObjectStoreUnavailable("Object storage is not configured.")
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            region_name=self.region,
            aws_access_key_id=self.access_key.get_secret_value(),
            aws_secret_access_key=self.secret_key.get_secret_value(),
        )

    async def presign_upload(
        self, *, key: str, media_type: str, content_hash: str, expires: int = 900
    ) -> UploadTicket:
        client = self._client()
        params = {
            "Bucket": self.bucket,
            "Key": key,
            "ContentType": media_type,
            "Metadata": {"sha256": content_hash.lower()},
            "ServerSideEncryption": "AES256",
        }
        url = await asyncio.to_thread(
            client.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=expires,
            HttpMethod="PUT",
        )
        return UploadTicket(
            url=url,
            required_headers={
                "Content-Type": media_type,
                "x-amz-meta-sha256": content_hash.lower(),
                "x-amz-server-side-encryption": "AES256",
            },
            expires_in_seconds=expires,
        )

    async def verify_upload(self, *, key: str, size_bytes: int, content_hash: str) -> None:
        client = self._client()
        head = await asyncio.to_thread(client.head_object, Bucket=self.bucket, Key=key)
        if int(head.get("ContentLength", -1)) != size_bytes:
            raise ValueError("Uploaded object size does not match its registration.")
        metadata = head.get("Metadata") or {}
        if str(metadata.get("sha256", "")).lower() != content_hash.lower():
            raise ValueError("Uploaded object hash metadata does not match its registration.")

    async def presign_download(self, *, key: str, expires: int = 300) -> str:
        client = self._client()
        return await asyncio.to_thread(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
            HttpMethod="GET",
        )

    async def delete(self, *, key: str) -> None:
        client = self._client()
        await asyncio.to_thread(client.delete_object, Bucket=self.bucket, Key=key)
