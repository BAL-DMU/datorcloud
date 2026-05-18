"""Component that wraps the MinIO Python client for object-storage operations."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from minio import Minio
from minio.error import S3Error

log = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "minio:9090"


class MinioObjectComponent:
    """Component for managing object storage operations with MinIO."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: bool = False,
        client: Optional["Minio"] = None,
    ) -> None:
        """Initialize MinIO client connection.

        Credentials are intentionally **not** defaulted. They must come from
        an injected ``client`` (typical for tests), explicit arguments, or
        the project's ``.env`` (loaded by the CLI / examples / Dagster
        resource that wraps this component).

        Args:
            endpoint: MinIO server endpoint (host:port, no scheme).
                Defaults to ``minio:9090`` when not provided.
            access_key: MinIO access key. **Required** when ``client`` is None.
            secret_key: MinIO secret key. **Required** when ``client`` is None.
            secure: Whether to use HTTPS.
            client: Optional pre-built MinIO client. When provided the other
                arguments are ignored. Useful for tests.

        Raises:
            ValueError: When ``client`` is None and credentials are missing.
        """
        if client is not None:
            self.client = client
            return

        if not access_key or not secret_key:
            raise ValueError(
                "MinIO credentials are required. Pass `access_key` and "
                "`secret_key` explicitly, inject a pre-built `client`, or "
                "set S3_ACCESS_KEY / S3_SECRET_KEY in your .env and build "
                "the orchestrator with DatorCloudOrchestrator.from_env()."
            )

        self.client = Minio(
            endpoint=endpoint or DEFAULT_ENDPOINT,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """Create a bucket if it doesn't exist.

        Returns ``True`` if the bucket exists (or was just created) and ``False``
        on a MinIO error.
        """
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
            return True
        except S3Error:
            log.exception("Error ensuring bucket %s exists", bucket_name)
            return False

    def upload_file(self, bucket_name: str, object_name: str, file_path: str) -> bool:
        """Upload a single file to MinIO."""
        try:
            self.ensure_bucket_exists(bucket_name)
            self.client.fput_object(bucket_name, object_name, file_path)
            return True
        except S3Error:
            log.exception("Error uploading file %s to %s/%s", file_path, bucket_name, object_name)
            return False

    def upload_directory(
        self,
        local_directory: str,
        bucket_name: str,
        prefix: str = "",
    ) -> List[Dict[str, str]]:
        """Recursively upload files from a local directory to MinIO."""
        uploaded_files: List[Dict[str, str]] = []
        self.ensure_bucket_exists(bucket_name)

        for root, _dirs, files in os.walk(local_directory):
            for filename in files:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, local_directory)
                object_name = os.path.join(prefix, relative_path).replace("\\", "/")
                try:
                    self.client.fput_object(bucket_name, object_name, local_path)
                    uploaded_files.append(
                        {
                            "local_path": local_path,
                            "bucket": bucket_name,
                            "object_name": object_name,
                            "status": "success",
                        }
                    )
                except S3Error as exc:
                    log.warning(
                        "Failed to upload %s to %s/%s: %s",
                        local_path,
                        bucket_name,
                        object_name,
                        exc,
                    )
                    uploaded_files.append(
                        {
                            "local_path": local_path,
                            "bucket": bucket_name,
                            "object_name": object_name,
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        return uploaded_files

    def download_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
    ) -> bool:
        """Download a file from MinIO."""
        try:
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.client.fget_object(bucket_name, object_name, file_path)
            return True
        except S3Error:
            log.exception(
                "Error downloading %s from bucket %s", object_name, bucket_name
            )
            return False
