"""High-level orchestrator that wires every DatorCloud component together."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd

from ..components.metadata_generator_component import MetadataGeneratorComponent
from ..components.metadata_storage_component import MetadataStorageComponent
from ..components.minio_component import MinioObjectComponent
from ..components.query_component import QueryComponent
from ..components.retrieval_component import ObjectRetrievalComponent

log = logging.getLogger(__name__)


class DatorCloudOrchestrator:
    """Main orchestrator class for DatorCloud operations.

    Coordinates the workflow between every component without forcing callers
    to assemble them by hand.
    """

    def __init__(
        self,
        minio_endpoint: str = "minio:9090",
        minio_access_key: str = "minioadmin",
        minio_secret_key: str = "minioadmin",
        minio_secure: bool = False,
        s3_region: str = "us-east-1",
        data_bucket: str = "orx-datalake",
        metadata_bucket: str = "orx-metadata",
        local_data_dir: str = "./data",
        local_download_dir: str = "./retrieved_data",
        duckdb_extension_path: Optional[str] = None,
        minio_component: Optional[MinioObjectComponent] = None,
        metadata_generator: Optional[MetadataGeneratorComponent] = None,
        metadata_storage: Optional[MetadataStorageComponent] = None,
        query_component: Optional[QueryComponent] = None,
        retrieval_component: Optional[ObjectRetrievalComponent] = None,
    ) -> None:
        """Initialize the orchestrator.

        Each component can be injected explicitly (handy for tests). When a
        component is not provided, a default one is built from the configuration
        parameters.
        """
        self.minio_component = minio_component or MinioObjectComponent(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure,
        )
        self.metadata_generator = (
            metadata_generator or MetadataGeneratorComponent()
        )
        self.query_component = query_component or QueryComponent(
            s3_region=s3_region,
            s3_endpoint=minio_endpoint,
            s3_access_key=minio_access_key,
            s3_secret_key=minio_secret_key,
            s3_use_ssl=minio_secure,
            duckdb_extension_path=duckdb_extension_path,
        )
        self.metadata_storage = metadata_storage or MetadataStorageComponent(
            minio_component=self.minio_component,
            metadata_bucket=metadata_bucket,
        )
        self.retrieval_component = (
            retrieval_component
            or ObjectRetrievalComponent(
                minio_component=self.minio_component,
                query_component=self.query_component,
                local_base_dir=local_download_dir,
            )
        )

        self.data_bucket = data_bucket
        self.metadata_bucket = metadata_bucket
        self.local_data_dir = local_data_dir
        self.local_download_dir = local_download_dir
        self._last_metadata_file: Optional[str] = None

    # ------------------------------------------------------------------
    # Workflow entry points
    # ------------------------------------------------------------------

    def upload_datasets(
        self,
        dataset_paths: Dict[str, str],
        bucket_name: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Upload one or more dataset directories to MinIO."""
        target_bucket = bucket_name or self.data_bucket
        self.minio_component.ensure_bucket_exists(target_bucket)

        results: Dict[str, List[Dict[str, Any]]] = {}
        for dataset_name, dataset_path in dataset_paths.items():
            if not os.path.exists(dataset_path):
                log.warning("Dataset path '%s' does not exist.", dataset_path)
                results[dataset_name] = []
                continue
            results[dataset_name] = self.minio_component.upload_directory(
                local_directory=dataset_path,
                bucket_name=target_bucket,
                prefix=dataset_name,
            )
        return results

    def generate_and_upload_metadata(
        self,
        dataset_dirs: Dict[str, str],
        output_file: str = "metadata.csv",
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Generate metadata for datasets and upload the CSV to MinIO."""
        return self.metadata_storage.create_metadata_and_store(
            metadata_generator_component=self.metadata_generator,
            dataset_dirs=dataset_dirs,
            local_file_path=output_file,
            bucket_name=bucket_name,
            object_name=object_name,
        )

    def query_metadata(
        self,
        metadata_file: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Query metadata from the metadata store."""
        if metadata_file is None:
            metadata_file = f"s3://{self.metadata_bucket}/metadata.csv"

        self._last_metadata_file = metadata_file
        return self.query_component.query_metadata(
            metadata_file=metadata_file,
            filters=filters,
            limit=limit,
        )

    def retrieve_data(
        self,
        dataset: str,
        metadata_file: Optional[str] = None,
        max_files: Optional[int] = None,
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve data based on a metadata query."""
        if metadata_file is None:
            metadata_file = (
                self._last_metadata_file
                or f"s3://{self.metadata_bucket}/metadata.csv"
            )
        return self.retrieval_component.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=self.data_bucket,
            max_files=max_files,
            **filters,
        )

    def retrieve_experiment(
        self,
        dataset: str,
        experiment: str,
        metadata_file: Optional[str] = None,
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve all data for a specific experiment."""
        if metadata_file is None:
            metadata_file = (
                self._last_metadata_file
                or f"s3://{self.metadata_bucket}/metadata.csv"
            )
        return self.retrieval_component.retrieve_experiment_data(
            metadata_file=metadata_file,
            dataset=dataset,
            experiment=experiment,
            data_bucket=self.data_bucket,
            **filters,
        )
