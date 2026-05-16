"""Dagster assets and resource for the DatorCloud component pipeline.

The four assets form a linear pipeline:

    upload_datasets -> generate_metadata -> query_metadata -> retrieve_objects

All assets share a single :class:`DatorCloudResource`, a Pydantic-based
``ConfigurableResource`` that lazily builds the underlying components. Per-asset
inputs (dataset paths, filters, limits, ...) are supplied through dedicated
``dagster.Config`` classes, which makes them configurable from ``run_config``
and keeps the asset function signatures Dagster-compatible.

Note: ``from __future__ import annotations`` is intentionally *not* used here.
Dagster's ``@asset`` decorator inspects runtime type annotations to wire up
``Config`` and resource parameters; stringified annotations break that
resolution.
"""

import logging
from typing import Any, Dict, List, Optional

from dagster import (
    AssetIn,
    Config,
    ConfigurableResource,
    MetadataValue,
    Output,
    asset,
)
from pydantic import Field

from ..components.metadata_generator_component import MetadataGeneratorComponent
from ..components.metadata_storage_component import MetadataStorageComponent
from ..components.minio_component import MinioObjectComponent
from ..components.query_component import QueryComponent
from ..components.retrieval_component import ObjectRetrievalComponent

log = logging.getLogger(__name__)


class DatorCloudResource(ConfigurableResource):
    """Dagster resource that exposes the DatorCloud components.

    Configuration values mirror :class:`datorcloud.core.DatorCloudOrchestrator`.

    ``ConfigurableResource`` instances are Pydantic models that Dagster may
    rebuild between contexts. Storing component instances directly on ``self``
    therefore does not survive a materialization. We instead build components
    on every access (they are cheap to construct) and expose a
    :meth:`build_orchestrator` helper that callers can use when they want a
    single object holding all of them.
    """

    minio_endpoint: str = "minio:9090"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    s3_region: str = "us-east-1"
    data_bucket: str = "orx-datalake"
    metadata_bucket: str = "orx-metadata"
    local_data_dir: str = "./data"
    local_download_dir: str = "./retrieved_data"
    duckdb_extension_path: Optional[str] = Field(
        default=None,
        description="Optional explicit path to the DuckDB httpfs extension.",
    )

    def _build_minio(self) -> MinioObjectComponent:
        return MinioObjectComponent(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            secure=self.minio_secure,
        )

    def _build_query(self) -> QueryComponent:
        return QueryComponent(
            s3_region=self.s3_region,
            s3_endpoint=self.minio_endpoint,
            s3_access_key=self.minio_access_key,
            s3_secret_key=self.minio_secret_key,
            s3_use_ssl=self.minio_secure,
            duckdb_extension_path=self.duckdb_extension_path,
        )

    @property
    def minio(self) -> MinioObjectComponent:
        return self._build_minio()

    @property
    def metadata_generator(self) -> MetadataGeneratorComponent:
        return MetadataGeneratorComponent()

    @property
    def metadata_storage(self) -> MetadataStorageComponent:
        return MetadataStorageComponent(
            minio_component=self.minio,
            metadata_bucket=self.metadata_bucket,
        )

    @property
    def query(self) -> QueryComponent:
        return self._build_query()

    @property
    def retrieval(self) -> ObjectRetrievalComponent:
        minio = self.minio
        return ObjectRetrievalComponent(
            minio_component=minio,
            query_component=self._build_query(),
            local_base_dir=self.local_download_dir,
        )

    def default_metadata_s3_path(self, object_name: str = "metadata.csv") -> str:
        return f"s3://{self.metadata_bucket}/{object_name}"


class UploadDatasetsConfig(Config):
    """Configuration for the ``upload_datasets`` asset."""

    dataset_paths: Dict[str, str]
    bucket_name: Optional[str] = None


class GenerateMetadataConfig(Config):
    """Configuration for the ``generate_metadata`` asset."""

    dataset_dirs: Dict[str, str]
    output_file: str = "./data/metadata.csv"
    bucket_name: Optional[str] = None
    object_name: str = "metadata.csv"


class QueryMetadataConfig(Config):
    """Configuration for the ``query_metadata`` asset."""

    filters: Dict[str, Any] = {}
    limit: Optional[int] = None
    metadata_file: Optional[str] = None


class RetrieveObjectsConfig(Config):
    """Configuration for the ``retrieve_objects`` asset."""

    dataset: str
    filters: Dict[str, Any] = {}
    max_files: Optional[int] = None
    metadata_file: Optional[str] = None


@asset
def upload_datasets(
    config: UploadDatasetsConfig,
    datorcloud: DatorCloudResource,
) -> Output[Dict[str, List[Dict[str, Any]]]]:
    """Upload one or more dataset directories to MinIO."""
    bucket = config.bucket_name or datorcloud.data_bucket
    datorcloud.minio.ensure_bucket_exists(bucket)

    results: Dict[str, List[Dict[str, Any]]] = {}
    for name, path in config.dataset_paths.items():
        results[name] = datorcloud.minio.upload_directory(
            local_directory=path,
            bucket_name=bucket,
            prefix=name,
        )

    total = sum(len(files) for files in results.values())
    successful = sum(
        len([f for f in files if f.get("status") == "success"])
        for files in results.values()
    )
    log.info("upload_datasets: %s/%s files uploaded", successful, total)
    return Output(
        results,
        metadata={
            "total_files": total,
            "successful_uploads": successful,
            "datasets": len(config.dataset_paths),
            "bucket": bucket,
        },
    )


@asset(ins={"upload_results": AssetIn("upload_datasets")})
def generate_metadata(
    config: GenerateMetadataConfig,
    datorcloud: DatorCloudResource,
    upload_results: Dict[str, List[Dict[str, Any]]],
) -> Output[Dict[str, Any]]:
    """Generate and upload metadata for the configured datasets."""
    df = datorcloud.metadata_storage.create_metadata_and_store(
        metadata_generator_component=datorcloud.metadata_generator,
        dataset_dirs=config.dataset_dirs,
        local_file_path=config.output_file,
        bucket_name=config.bucket_name,
        object_name=config.object_name,
    )
    payload = {
        "record_count": int(len(df)),
        "datasets": list(config.dataset_dirs.keys()),
        "columns": list(df.columns),
        "output_file": config.output_file,
        "metadata_file": datorcloud.default_metadata_s3_path(config.object_name),
    }
    return Output(
        payload,
        metadata={
            "record_count": payload["record_count"],
            "datasets": MetadataValue.json(payload["datasets"]),
            "columns": MetadataValue.json(payload["columns"]),
            "object_name": config.object_name,
        },
    )


@asset(ins={"metadata_info": AssetIn("generate_metadata")})
def query_metadata(
    config: QueryMetadataConfig,
    datorcloud: DatorCloudResource,
    metadata_info: Dict[str, Any],
) -> Output[Dict[str, Any]]:
    """Query the metadata file with the configured filters."""
    metadata_file = config.metadata_file or metadata_info.get(
        "metadata_file", datorcloud.default_metadata_s3_path()
    )
    df = datorcloud.query.query_metadata(
        metadata_file=metadata_file,
        filters=config.filters or None,
        limit=config.limit,
    )
    payload = {
        "metadata_file": metadata_file,
        "result_count": int(len(df)),
        "filters": config.filters,
        "results": df.to_dict(orient="records"),
    }
    return Output(
        payload,
        metadata={
            "result_count": payload["result_count"],
            "filters_applied": MetadataValue.json(config.filters),
            "metadata_file": metadata_file,
        },
    )


@asset(ins={"query_results": AssetIn("query_metadata")})
def retrieve_objects(
    config: RetrieveObjectsConfig,
    datorcloud: DatorCloudResource,
    query_results: Dict[str, Any],
) -> Output[List[Dict[str, Any]]]:
    """Download the objects matched by the previous query."""
    metadata_file = (
        config.metadata_file
        or query_results.get("metadata_file")
        or datorcloud.default_metadata_s3_path()
    )
    downloaded = datorcloud.retrieval.retrieve_objects(
        metadata_file=metadata_file,
        dataset=config.dataset,
        data_bucket=datorcloud.data_bucket,
        max_files=config.max_files,
        **config.filters,
    )
    successful = sum(1 for f in downloaded if f.get("success"))
    return Output(
        downloaded,
        metadata={
            "total_files": len(downloaded),
            "successful_downloads": successful,
            "dataset": config.dataset,
            "filters": MetadataValue.json(config.filters),
        },
    )


component_assets = [
    upload_datasets,
    generate_metadata,
    query_metadata,
    retrieve_objects,
]


# ---------------------------------------------------------------------------
# Backwards-compatible alias
# ---------------------------------------------------------------------------


class DatorCloudComponents(DatorCloudResource):
    """Deprecated alias for :class:`DatorCloudResource`.

    Retained for code written against the original component branch.
    """
