#!/usr/bin/env python
"""Example Dagster workspace for the DatorCloud component pipeline.

``DatorCloudResource`` reads its connection and storage defaults straight from
the environment (see ``.env.example``). Calling it with no arguments is the
recommended way to pick up the project's ``.env``; pass keyword arguments to
override individual fields.

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


DATA_LAKE_PATH = _env("DATA_LAKE_PATH", "./data_lake")
RETRIEVED_DATA_PATH = _env("RETRIEVED_DATA_PATH", "./retrieved_data")
DATA_BUCKET = _env("DATA_BUCKET", "orx-datalake")
METADATA_BUCKET = _env("METADATA_BUCKET", "orx-metadata")


datorcloud_resource = DatorCloudResource(
    data_bucket=DATA_BUCKET,
    metadata_bucket=METADATA_BUCKET,
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
                    "bucket_name": DATA_BUCKET,
                }
            },
            "generate_metadata": {
                "config": {
                    "dataset_dirs": {
                        "4dor-dataset": os.path.join(DATA_LAKE_PATH, "4dor-dataset"),
                        "orx-experiments": os.path.join(DATA_LAKE_PATH, "orx-experiments"),
                    },
                    "output_file": os.path.join(DATA_LAKE_PATH, "metadata_orx-datahub.csv"),
                    "bucket_name": METADATA_BUCKET,
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
