"""Component that wraps the MinIO Python client for object-storage operations."""

from __future__ import annotations

import logging
import os
from typing import Dict, List

from minio import Minio
from minio.error import S3Error

log = logging.getLogger(__name__)


class MinioObjectComponent:
    """Component for managing object storage operations with MinIO."""

    def __init__(
        self,
        endpoint: str = "minio:9090",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool = False,
        client: "Minio | None" = None,
    ) -> None:
        """Initialize MinIO client connection.

        Args:
            endpoint: MinIO server endpoint.
            access_key: MinIO access key.
            secret_key: MinIO secret key.
            secure: Whether to use HTTPS.
            client: Optional pre-built MinIO client. Useful for tests.
        """
        if client is not None:
            self.client = client
        else:
            self.client = Minio(
                endpoint=endpoint,
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
