#!/usr/bin/env python
"""
Basic example of using DatorCloud Components to:
1. Upload datasets to MinIO
2. Generate metadata
3. Query metadata 
4. Retrieve data based on query
"""

import os
from datorcloud import (
    MinioObjectComponent,
    MetadataGeneratorComponent,
    MetadataQueryComponent,
    ObjectRetrievalComponent
)

# Initialize MinIO component
minio_component = MinioObjectComponent(
    endpoint="minio:9090",
    bucket_name="orx-datalake"
)

# Initialize the metadata component
metadata_component = MetadataGeneratorComponent(
    output_file="./data/metadata_orx-datahub.csv",
    minio_component=minio_component,
    metadata_bucket="orx-metadata"
)

# Initialize query component
query_component = MetadataQueryComponent(
    minio_component=minio_component,
    metadata_bucket="orx-metadata"
)

# Initialize retrieval component
retrieval_component = ObjectRetrievalComponent(
    minio_component=minio_component,
    local_download_dir="./data/retrieved"
)

# Define dataset paths
dataset_paths = {
    "4dor-dataset": "./data/4dor-dataset",
    "orx-experiments": "./data/orx-experiments"
}

# 1. Upload datasets to MinIO
print("Uploading datasets to MinIO...")
upload_results = {}
for dataset_name, directory_path in dataset_paths.items():
    uploaded_files = minio_component.upload_directory(
        directory_path=directory_path,
        object_prefix=f"{dataset_name}/"
    )
    upload_results[dataset_name] = uploaded_files

print(f"Upload complete. Processed {sum(len(files) for files in upload_results.values())} files.")

# 2. Generate and upload metadata
print("\nGenerating metadata...")
metadata_df = metadata_component.generate_metadata(
    dataset_dirs=dataset_paths
)
print(f"Metadata generated with {len(metadata_df)} records.")

# Upload metadata to MinIO
metadata_component.upload_metadata()
print("Metadata uploaded to MinIO.")

# 3. Query metadata for a specific camera
print("\nQuerying metadata for camera01...")
results = query_component.query_metadata(
    filters={"camera_id": "camera01"},
    limit=10
)
print(f"Found {len(results)} records. Sample data:")
print(results.head())

# 4. Retrieve files for an experiment
print("\nRetrieving data for a specific experiment...")
dataset = "4dor-dataset"
experiment = results["experiment"].iloc[0] if not results.empty else None

if experiment:
    downloaded_files = retrieval_component.retrieve_objects(
        metadata_df=results[results["dataset"] == dataset],
        max_files=5
    )
    print(f"Downloaded {len(downloaded_files)} files from experiment '{experiment}'")
    for file_info in downloaded_files:
        print(f"  - {file_info['local_path']} (Success: {file_info['success']})")
else:
    print("No experiments found in the query results.") 
