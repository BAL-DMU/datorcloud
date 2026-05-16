#!/usr/bin/env python
"""Example Dagster workspace for the DatorCloud component pipeline.

Load with the Dagster CLI:

    dagster dev -f examples/dagster_workflow.py

or, when running the file directly, execute the job in-process.
"""

from __future__ import annotations

from dagster import AssetSelection, Definitions, define_asset_job

from datorcloud.dagster import (
    DatorCloudResource,
    component_assets,
)

datorcloud_resource = DatorCloudResource(
    minio_endpoint="minio:9090",
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
    local_data_dir="./data",
    local_download_dir="./retrieved_data",
)

datorcloud_job = define_asset_job(
    name="datorcloud_workflow_job",
    selection=AssetSelection.assets(*component_assets),
)

defs = Definitions(
    assets=component_assets,
    jobs=[datorcloud_job],
    resources={"datorcloud": datorcloud_resource},
)


if __name__ == "__main__":
    run_config = {
        "ops": {
            "upload_datasets": {
                "config": {
                    "dataset_paths": {
                        "4dor-dataset": "./data/4dor-dataset",
                        "orx-experiments": "./data/orx-experiments",
                    },
                    "bucket_name": "orx-datalake",
                }
            },
            "generate_metadata": {
                "config": {
                    "dataset_dirs": {
                        "4dor-dataset": "./data/4dor-dataset",
                        "orx-experiments": "./data/orx-experiments",
                    },
                    "output_file": "./data/metadata_orx-datahub.csv",
                    "bucket_name": "orx-metadata",
                    "object_name": "metadata_orx-datahub.csv",
                }
            },
            "query_metadata": {
                "config": {
                    "filters": {
                        "camera_id": "camera01",
                        "image_type": "colorimage",
                    },
                    "limit": 10,
                }
            },
            "retrieve_objects": {
                "config": {
                    "dataset": "4dor-dataset",
                    "max_files": 5,
                    "filters": {
                        "camera_id": "camera01",
                        "image_type": "colorimage",
                    },
                }
            },
        }
    }

    result = datorcloud_job.execute_in_process(run_config=run_config)
    print(f"Job completed with status: {result.success}")
