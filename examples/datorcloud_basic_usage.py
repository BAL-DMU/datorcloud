#!/usr/bin/env python
"""Basic example of using DatorCloud components to:

1. Upload datasets to MinIO
2. Generate and store metadata
3. Query metadata
4. Retrieve data based on the query

All connection settings and storage paths are read from the project ``.env``
file (see ``.env.example`` for the full list of variables).
"""

import logging
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from datorcloud import (
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    MinioObjectComponent,
    ObjectRetrievalComponent,
    QueryComponent,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("datorcloud.examples.basic")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _endpoint() -> str:
    """Strip the scheme from ``S3_ENDPOINT`` (the Minio SDK wants host:port)."""
    raw = _env("S3_ENDPOINT", "minio:9090")
    return raw.replace("http://", "").replace("https://", "")


def main() -> None:
    data_bucket = "orx-datalake"
    metadata_bucket = "orx-metadata"
    metadata_filename = "metadata_orx-datahub.csv"

    data_lake = _env("DATA_LAKE_PATH", "./data_lake")
    retrieved_dir = _env("RETRIEVED_DATA_PATH", "./retrieved_data")

    local_metadata_path = os.path.join(data_lake, metadata_filename)
    metadata_s3_path = f"s3://{metadata_bucket}/{metadata_filename}"

    minio_component = MinioObjectComponent(
        endpoint=_endpoint(),
        access_key=_env("S3_ACCESS_KEY", "minioadmin"),
        secret_key=_env("S3_SECRET_KEY", "minioadmin"),
    )
    metadata_generator = MetadataGeneratorComponent()
    metadata_storage = MetadataStorageComponent(
        minio_component=minio_component,
        metadata_bucket=metadata_bucket,
    )
    query_component = QueryComponent(
        s3_endpoint=_endpoint(),
        s3_access_key=_env("S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=_env("S3_SECRET_KEY", "minioadmin"),
    )
    retrieval_component = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=query_component,
        local_base_dir=retrieved_dir,
    )

    dataset_paths = {
        "4dor-dataset": os.path.join(data_lake, "4dor-dataset"),
        "orx-experiments": os.path.join(data_lake, "orx-experiments"),
    }

    log.info("Uploading datasets to MinIO...")
    minio_component.ensure_bucket_exists(data_bucket)
    upload_results = {}
    for dataset_name, directory_path in dataset_paths.items():
        if not os.path.exists(directory_path):
            log.warning("Dataset path %s does not exist, skipping.", directory_path)
            continue
        upload_results[dataset_name] = minio_component.upload_directory(
            local_directory=directory_path,
            bucket_name=data_bucket,
            prefix=dataset_name,
        )
    total = sum(len(v) for v in upload_results.values())
    log.info("Upload complete (%s files processed).", total)

    log.info("Generating and uploading metadata...")
    metadata_df = metadata_storage.create_metadata_and_store(
        metadata_generator_component=metadata_generator,
        dataset_dirs=dataset_paths,
        local_file_path=local_metadata_path,
        object_name=metadata_filename,
    )
    log.info("Generated metadata with %s records.", len(metadata_df))

    log.info("Querying metadata for camera01...")
    results = query_component.query_metadata(
        metadata_file=metadata_s3_path,
        filters={"camera_id": "camera01"},
        limit=10,
    )
    log.info("Found %s records.", len(results))

    if not results.empty:
        experiment = results["experiment"].iloc[0]
        log.info("Retrieving files for experiment %s ...", experiment)
        downloaded = retrieval_component.retrieve_experiment_data(
            metadata_file=metadata_s3_path,
            dataset="4dor-dataset",
            experiment=experiment,
            data_bucket=data_bucket,
            camera_id="camera01",
        )
        log.info("Downloaded %s files.", len(downloaded))
    else:
        log.info("No records matched the query; skipping retrieval.")


if __name__ == "__main__":
    main()
