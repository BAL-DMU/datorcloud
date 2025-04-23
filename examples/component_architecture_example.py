#!/usr/bin/env python
"""
Example using DatorCloud's Component-Oriented Architecture.
"""

import os
from datorcloud.core.datorcloud_orchestrator import DatorCloudOrchestrator
from datorcloud.components.minio_component import MinioObjectComponent
from datorcloud.components.metadata_generator_component import MetadataGeneratorComponent
from datorcloud.components.metadata_storage_component import MetadataStorageComponent
from datorcloud.components.query_component import QueryComponent
from datorcloud.components.retrieval_component import ObjectRetrievalComponent

def main():
    # Method 1: Using the orchestrator (recommended for most use cases)
    print("== Using the DatorCloudOrchestrator ==")
    orchestrator_example()
    
    # Method 2: Using individual components (for more granular control)
    print("\n== Using Individual Components ==")
    component_example()


def orchestrator_example():
    """Example workflow using the DatorCloudOrchestrator."""
    # Initialize the orchestrator
    orchestrator = DatorCloudOrchestrator(
        minio_endpoint="minio:9090",
        data_bucket="orx-datalake",
        metadata_bucket="orx-metadata"
    )
    
    # Define dataset paths
    dataset_paths = {
        "4dor-dataset": "./data/4dor-dataset",
        "orx-experiments": "./data/orx-experiments"
    }
    
    # Define metadata filename (used consistently throughout)
    metadata_filename = "metadata_orx-datahub.csv"
    local_metadata_path = f"./data/{metadata_filename}"
    
    # 1. Upload datasets
    print("1. Uploading datasets...")
    upload_results = orchestrator.upload_datasets(dataset_paths)
    processed_files = sum(len(files) for files in upload_results.values())
    print(f"   Processed {processed_files} files.")
    
    # 2. Generate and upload metadata
    print("2. Generating and uploading metadata...")
    metadata_df = orchestrator.generate_and_upload_metadata(
        dataset_dirs=dataset_paths,
        output_file=local_metadata_path,
        object_name=metadata_filename  # Explicitly specify the object name in MinIO
    )
    print(f"   Generated metadata with {len(metadata_df)} records.")
    
    # 3. Query metadata with error handling
    print("3. Querying metadata...")
    metadata_s3_path = f"s3://{orchestrator.metadata_bucket}/{metadata_filename}"
    
    try:
        results = orchestrator.query_metadata(
            metadata_file=metadata_s3_path,
            filters={"camera_id": "camera01"},
            limit=10
        )
        print(f"   Found {len(results)} records.")
        
        # 4. Retrieve files only if results found
        if not results.empty:
            print("4. Retrieving files...")
            experiment = results["experiment"].iloc[0]
            downloaded_files = orchestrator.retrieve_experiment(
                dataset="4dor-dataset",
                experiment=experiment,
                camera_id="camera01",
                max_files=5
            )
            print(f"   Downloaded {len(downloaded_files)} files.")
        else:
            print("   No records found matching the query criteria.")
    except Exception as e:
        print(f"   Error querying metadata: {e}")
        print("   Verify that the metadata file was successfully uploaded to MinIO.")
        # Continue with empty results
        print("   Skipping file retrieval step due to query error.")


def component_example():
    """Example workflow using individual components directly."""
    # Initialize individual components
    minio_component = MinioObjectComponent(
        endpoint="minio:9090",
        access_key="minioadmin",
        secret_key="minioadmin"
    )
    
    metadata_generator = MetadataGeneratorComponent()
    
    query_component = QueryComponent(
        s3_endpoint="minio:9090",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin"
    )
    
    metadata_storage = MetadataStorageComponent(
        minio_component=minio_component,
        metadata_bucket="orx-metadata"
    )
    
    retrieval_component = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=query_component,
        local_base_dir="./retrieved_data"
    )
    
    #######################################
    # Define dataset paths and bucket names
    dataset_paths = {
        "4dor-dataset": "./data/4dor-dataset",
        "orx-experiments": "./data/orx-experiments"
    }
    data_bucket = "orx-datalake"
    metadata_bucket = "orx-metadata"
    metadata_filename = "component_metadata.csv"
    metadata_file_path = f"./data/{metadata_filename}"
    metadata_s3_path = f"s3://{metadata_bucket}/{metadata_filename}"
    
    # 1. Upload datasets
    print("1. Uploading datasets directly with MinioObjectComponent...")
    # Ensure bucket exists
    minio_component.ensure_bucket_exists(data_bucket)
    
    # Upload each dataset
    processed_files = 0
    for dataset_name, dataset_path in dataset_paths.items():
        if os.path.exists(dataset_path):
            results = minio_component.upload_directory(
                local_directory=dataset_path,
                bucket_name=data_bucket,
                prefix=dataset_name
            )
            processed_files += len(results)
    
    print(f"   Processed {processed_files} files.")
    
    # 2. Generate and store metadata
    print("2. Generating metadata with MetadataGeneratorComponent...")
    metadata = metadata_storage.create_metadata_and_store(
        metadata_generator_component=metadata_generator,
        dataset_dirs=dataset_paths,
        local_file_path=metadata_file_path,
        bucket_name=metadata_bucket,
        object_name=metadata_filename
    )
    print(f"   Generated metadata with {len(metadata)} records.")
    
    # 3. Query metadata
    print("3. Querying metadata with QueryComponent...")
    results = query_component.query_metadata(
        metadata_file=metadata_s3_path,
        filters={"camera_id": "camera01"},
        limit=5
    )
    print(f"   Found {len(results)} records.")
    
    # 4. Retrieve files
    if not results.empty:
        print("4. Retrieving files with ObjectRetrievalComponent...")
        experiment = results["experiment"].iloc[0]
        # Add experiment to filters
        filters = {"experiment": experiment, "camera_id": "camera01"}
        
        downloaded_files = retrieval_component.retrieve_objects(
            metadata_file=metadata_s3_path,
            dataset="4dor-dataset",
            data_bucket=data_bucket,
            max_files=3,
            **filters
        )
        print(f"   Downloaded {len(downloaded_files)} files.")

    # After uploading metadata
    print("   Verifying metadata file in MinIO...")
    try:
        # Use the minio_component to check if the object exists
        stat = minio_component.client.stat_object(metadata_bucket, metadata_filename)
        print(f"   Metadata file exists in MinIO: {metadata_filename}")
    except Exception as e:
        print(f"   Warning: Could not verify metadata file in MinIO: {e}")


if __name__ == "__main__":
    main() 
