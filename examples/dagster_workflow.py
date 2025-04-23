#!/usr/bin/env python
"""
Example of setting up a Dagster workflow with DatorCloud assets.
"""

from dagster import Definitions, define_asset_job, AssetSelection
from datorcloud.dagster import (
    DatorCloudComponents,
    upload_datasets,
    generate_metadata,
    query_metadata,
    retrieve_objects,
    component_assets
)


# Define the resource configuration
dator_components = DatorCloudComponents(
    minio_endpoint="minio:9090",
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
    local_data_dir="./data",
    local_download_dir="./retrieved_data"
)

# Create a job that processes all assets in sequence
datorcloud_job = define_asset_job(
    name="datorcloud_workflow_job",
    selection=AssetSelection.assets(*component_assets)
)

# Create the Dagster definitions
defs = Definitions(
    assets=component_assets,
    jobs=[datorcloud_job],
    resources={
        "components": dator_components
    }
)

# If running this file directly, execute the job
if __name__ == "__main__":
    result = datorcloud_job.execute_in_process(
        run_config={
            "ops": {
                "upload_datasets": {
                    "config": {
                        "dataset_paths": {
                            "4dor-dataset": "./data/4dor-dataset",
                            "orx-experiments": "./data/orx-experiments"
                        },
                        "bucket_name": "orx-datalake"
                    }
                },
                "generate_metadata": {
                    "config": {
                        "dataset_dirs": {
                            "4dor-dataset": "./data/4dor-dataset",
                            "orx-experiments": "./data/orx-experiments"
                        },
                        "output_file": "./data/metadata_orx-datahub.csv",
                        "bucket_name": "orx-metadata",
                        "object_name": "metadata_orx-datahub.csv"
                    }
                },
                "query_metadata": {
                    "config": {
                        "filters": {
                            "camera_id": "camera01",
                            "image_type": "colorimage"
                        },
                        "limit": 10
                    }
                },
                "retrieve_objects": {
                    "config": {
                        "dataset": "4dor-dataset",
                        "max_files": 5,
                        "camera_id": "camera01",
                        "image_type": "colorimage"
                    }
                }
            }
        }
    )
    
    print(f"Job completed with status: {result.success}") 
