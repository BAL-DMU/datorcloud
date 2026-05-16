#!/usr/bin/env python
"""Example using DatorCloud's Component-Oriented Architecture.

Connection settings and storage paths are read from the project ``.env`` file
(see ``.env.example``).
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from datorcloud.components.metadata_generator_component import MetadataGeneratorComponent
from datorcloud.components.metadata_storage_component import MetadataStorageComponent
from datorcloud.components.minio_component import MinioObjectComponent
from datorcloud.components.query_component import QueryComponent
from datorcloud.components.retrieval_component import ObjectRetrievalComponent
from datorcloud.core.datorcloud_orchestrator import DatorCloudOrchestrator


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _endpoint() -> str:
    raw = _env("S3_ENDPOINT", "minio:9090")
    return raw.replace("http://", "").replace("https://", "")


DATA_LAKE_PATH = _env("DATA_LAKE_PATH", "./data_lake")
RETRIEVED_DATA_PATH = _env("RETRIEVED_DATA_PATH", "./retrieved_data")


def main():
    print("== Using the DatorCloudOrchestrator ==")
    orchestrator_example()

    print("\n== Using Individual Components ==")
    component_example()


def orchestrator_example():
    """Example workflow using the DatorCloudOrchestrator."""
    orchestrator = DatorCloudOrchestrator(
        minio_endpoint=_endpoint(),
        minio_access_key=_env("S3_ACCESS_KEY", "minioadmin"),
        minio_secret_key=_env("S3_SECRET_KEY", "minioadmin"),
        data_bucket="orx-datalake",
        metadata_bucket="orx-metadata",
        local_data_dir=DATA_LAKE_PATH,
        local_download_dir=RETRIEVED_DATA_PATH,
    )

    dataset_paths = {
        "4dor-dataset": os.path.join(DATA_LAKE_PATH, "4dor-dataset"),
        "orx-experiments": os.path.join(DATA_LAKE_PATH, "orx-experiments"),
    }

    metadata_filename = "metadata_orx-datahub.csv"
    local_metadata_path = os.path.join(DATA_LAKE_PATH, metadata_filename)

    print("1. Uploading datasets...")
    upload_results = orchestrator.upload_datasets(dataset_paths)
    processed_files = sum(len(files) for files in upload_results.values())
    print(f"   Processed {processed_files} files.")

    print("2. Generating and uploading metadata...")
    metadata_df = orchestrator.generate_and_upload_metadata(
        dataset_dirs=dataset_paths,
        output_file=local_metadata_path,
        object_name=metadata_filename,
    )
    print(f"   Generated metadata with {len(metadata_df)} records.")

    print("3. Querying metadata...")
    metadata_s3_path = f"s3://{orchestrator.metadata_bucket}/{metadata_filename}"

    try:
        results = orchestrator.query_metadata(
            metadata_file=metadata_s3_path,
            filters={"camera_id": "camera01"},
            limit=10,
        )
        print(f"   Found {len(results)} records.")

        if not results.empty:
            print("4. Retrieving files...")
            experiment = results["experiment"].iloc[0]
            downloaded_files = orchestrator.retrieve_experiment(
                dataset="4dor-dataset",
                experiment=experiment,
                camera_id="camera01",
                max_files=5,
            )
            print(f"   Downloaded {len(downloaded_files)} files.")
        else:
            print("   No records found matching the query criteria.")
    except Exception as e:
        print(f"   Error querying metadata: {e}")
        print("   Verify that the metadata file was successfully uploaded to MinIO.")
        print("   Skipping file retrieval step due to query error.")


def component_example():
    """Example workflow using individual components directly."""
    minio_component = MinioObjectComponent(
        endpoint=_endpoint(),
        access_key=_env("S3_ACCESS_KEY", "minioadmin"),
        secret_key=_env("S3_SECRET_KEY", "minioadmin"),
    )
    metadata_generator = MetadataGeneratorComponent()
    query_component = QueryComponent(
        s3_endpoint=_endpoint(),
        s3_access_key=_env("S3_ACCESS_KEY", "minioadmin"),
        s3_secret_key=_env("S3_SECRET_KEY", "minioadmin"),
    )
    metadata_storage = MetadataStorageComponent(
        minio_component=minio_component,
        metadata_bucket="orx-metadata",
    )
    retrieval_component = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=query_component,
        local_base_dir=RETRIEVED_DATA_PATH,
    )

    dataset_paths = {
        "4dor-dataset": os.path.join(DATA_LAKE_PATH, "4dor-dataset"),
        "orx-experiments": os.path.join(DATA_LAKE_PATH, "orx-experiments"),
    }
    data_bucket = "orx-datalake"
    metadata_bucket = "orx-metadata"
    metadata_filename = "component_metadata.csv"
    metadata_file_path = os.path.join(DATA_LAKE_PATH, metadata_filename)
    metadata_s3_path = f"s3://{metadata_bucket}/{metadata_filename}"

    print("1. Uploading datasets directly with MinioObjectComponent...")
    minio_component.ensure_bucket_exists(data_bucket)

    processed_files = 0
    for dataset_name, dataset_path in dataset_paths.items():
        if os.path.exists(dataset_path):
            results = minio_component.upload_directory(
                local_directory=dataset_path,
                bucket_name=data_bucket,
                prefix=dataset_name,
            )
            processed_files += len(results)

    print(f"   Processed {processed_files} files.")

    print("2. Generating metadata with MetadataGeneratorComponent...")
    metadata = metadata_storage.create_metadata_and_store(
        metadata_generator_component=metadata_generator,
        dataset_dirs=dataset_paths,
        local_file_path=metadata_file_path,
        bucket_name=metadata_bucket,
        object_name=metadata_filename,
    )
    print(f"   Generated metadata with {len(metadata)} records.")

    print("3. Querying metadata with QueryComponent...")
    results = query_component.query_metadata(
        metadata_file=metadata_s3_path,
        filters={"camera_id": "camera01"},
        limit=5,
    )
    print(f"   Found {len(results)} records.")

    if not results.empty:
        print("4. Retrieving files with ObjectRetrievalComponent...")
        experiment = results["experiment"].iloc[0]
        filters = {"experiment": experiment, "camera_id": "camera01"}

        downloaded_files = retrieval_component.retrieve_objects(
            metadata_file=metadata_s3_path,
            dataset="4dor-dataset",
            data_bucket=data_bucket,
            max_files=3,
            **filters,
        )
        print(f"   Downloaded {len(downloaded_files)} files.")

    print("   Verifying metadata file in MinIO...")
    try:
        minio_component.client.stat_object(metadata_bucket, metadata_filename)
        print(f"   Metadata file exists in MinIO: {metadata_filename}")
    except Exception as e:
        print(f"   Warning: Could not verify metadata file in MinIO: {e}")


if __name__ == "__main__":
    main()
