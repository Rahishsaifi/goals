from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

_AZURITE_CONNECTION = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)


@dataclass(frozen=True)
class UploadGrant:
    container: str
    blob_name: str
    upload_url: str
    expires_at: datetime


def _parse_connection_parts(connection_string: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for item in connection_string.split(";"):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key] = value
    return parts


class BlobStorage:
    """Private blob access. Local APP_ENV uses Azurite; poc/cloud uses Azure Storage."""

    def __init__(self, connection_string: str | None = None) -> None:
        app_env = os.environ.get("APP_ENV", "local").lower()
        env_connection = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if connection_string:
            self.connection_string = connection_string
        elif app_env == "local":
            # Never use paid Azure Storage from a leftover shell env during local runs.
            self.connection_string = _AZURITE_CONNECTION
        else:
            self.connection_string = env_connection or _AZURITE_CONNECTION

        parts = _parse_connection_parts(self.connection_string)
        self.account_name = parts.get("AccountName", "devstoreaccount1")
        self.account_key = parts.get(
            "AccountKey",
            "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
            "K1SZFPTOtr/KBHBeksoGMGw==",
        )
        self.blob_endpoint = parts.get(
            "BlobEndpoint",
            f"https://{self.account_name}.blob.core.windows.net",
        ).rstrip("/")
        try:
            self._client = BlobServiceClient.from_connection_string(self.connection_string)
        except ValueError as exc:
            raise ValueError(
                "Invalid AZURE_STORAGE_CONNECTION_STRING. "
                "For local development, set APP_ENV=local to use Azurite."
            ) from exc

    def ensure_container(self, name: str) -> None:
        container = self._client.get_container_client(name)
        if not container.exists():
            container.create_container()

    def create_upload_grant(
        self, *, container: str, blob_name: str, content_type: str, ttl_minutes: int = 15
    ) -> UploadGrant:
        self.ensure_container(container)
        expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        sas = generate_blob_sas(
            account_name=self.account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=self.account_key,
            permission=BlobSasPermissions(create=True, write=True),
            expiry=expires,
            content_type=content_type,
        )
        encoded_blob = quote(blob_name, safe="/")
        url = f"{self.blob_endpoint}/{container}/{encoded_blob}?{sas}"
        return UploadGrant(
            container=container, blob_name=blob_name, upload_url=url, expires_at=expires
        )

    def create_download_url(
        self,
        *,
        container: str,
        blob_name: str,
        filename: str,
        content_type: str,
        ttl_minutes: int = 10,
    ) -> str:
        sas = generate_blob_sas(
            account_name=self.account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=self.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
            content_disposition=f'attachment; filename="{filename}"',
            content_type=content_type,
        )
        encoded_blob = quote(blob_name, safe="/")
        return f"{self.blob_endpoint}/{container}/{encoded_blob}?{sas}"

    def download_bytes(self, *, container: str, blob_name: str) -> bytes:
        blob = self._client.get_blob_client(container=container, blob=blob_name)
        return blob.download_blob().readall()

    def upload_bytes(
        self, *, container: str, blob_name: str, data: bytes, content_type: str
    ) -> None:
        self.ensure_container(container)
        blob = self._client.get_blob_client(container=container, blob=blob_name)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def delete_blob(self, *, container: str, blob_name: str) -> None:
        blob = self._client.get_blob_client(container=container, blob=blob_name)
        blob.delete_blob(delete_snapshots="include")
