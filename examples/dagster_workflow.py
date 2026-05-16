#!/usr/bin/env python
"""Example Dagster workspace for the DatorCloud component pipeline.

Connection settings and storage paths are read from the project ``.env`` file
(see ``.env.example``).

Load with the Dagster CLI:

    dagster dev -f examples/dagster_workflow.py

or, when running the file directly, execute the job in-process.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from dagster import AssetSelection, Definitions, define_asset_job

from datorcloud.dagster import (
    DatorCloudResource,
    component_assets,
)


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _endpoint() -> str:
    raw = _env("S3_ENDPOINT", "minio:9090")
    return raw.replace("http://", "").replace("https://", "")


DATA_LAKE_PATH = _env("DATA_LAKE_PATH", "./data_lake")
RETRIEVED_DATA_PATH = _env("RETRIEVED_DATA_PATH", "./retrieved_data")


datorcloud_resource = DatorCloudResource(
    minio_endpoint=_endpoint(),
    minio_access_key=_env("S3_ACCESS_KEY", "minioadmin"),
    minio_secret_key=_env("S3_SECRET_KEY", "minioadmin"),
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
    local_data_dir=DATA_LAKE_PATH,
    local_download_dir=RETRIEVED_DATA_PATH,
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
                        "4dor-dataset": os.path.join(DATA_LAKE_PATH, "4dor-dataset"),
                        "orx-experiments": os.path.join(DATA_LAKE_PATH, "orx-experiments"),
                    },
                    "bucket_name": "orx-datalake",
                }
            },
            "generate_metadata": {
                "config": {
                    "dataset_dirs": {
                        "4dor-dataset": os.path.join(DATA_LAKE_PATH, "4dor-dataset"),
                        "orx-experiments": os.path.join(DATA_LAKE_PATH, "orx-experiments"),
                    },
                    "output_file": os.path.join(DATA_LAKE_PATH, "metadata_orx-datahub.csv"),
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
