"""Component that writes generated metadata locally and uploads it to MinIO."""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import pandas as pd

from .minio_component import MinioObjectComponent

log = logging.getLogger(__name__)


class MetadataStorageComponent:
    """Component for managing metadata storage in MinIO."""

    def __init__(
        self,
        minio_component: MinioObjectComponent,
        metadata_bucket: str = "orx-metadata",
    ) -> None:
        self.minio_component = minio_component
        self.metadata_bucket = metadata_bucket

    def store_metadata(
        self,
        metadata_df: pd.DataFrame,
        local_file_path: str,
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None,
    ) -> bool:
        """Write ``metadata_df`` to ``local_file_path`` and upload it to MinIO."""
        target_bucket = bucket_name or self.metadata_bucket

        parent = os.path.dirname(local_file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            metadata_df.to_csv(local_file_path, index=False)
        except Exception:
            log.exception("Error saving metadata to local file %s", local_file_path)
            return False

        target_object = object_name or os.path.basename(local_file_path)
        return self.minio_component.upload_file(
            bucket_name=target_bucket,
            object_name=target_object,
            file_path=local_file_path,
        )

    def create_metadata_and_store(
        self,
        metadata_generator_component,
        dataset_dirs: Dict[str, str],
        local_file_path: str,
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Generate metadata and store it in MinIO in one call."""
        metadata_df = metadata_generator_component.generate_metadata(
            dataset_dirs=dataset_dirs,
            output_file=local_file_path,
        )
        success = self.store_metadata(
            metadata_df=metadata_df,
            local_file_path=local_file_path,
            bucket_name=bucket_name,
            object_name=object_name,
        )
        if not success:
            log.warning(
                "Metadata was generated but could not be stored in MinIO (bucket=%s).",
                bucket_name or self.metadata_bucket,
            )
        return metadata_df
