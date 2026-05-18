#!/usr/bin/env python
"""Dagster workspace mirroring the two DatorCloud operational workflows.

This file materialises the two pipelines documented in the DatorCloud
architecture diagram (see ``docs/03_components/architecture.md``) on the
bundled ``4dor-dataset`` under ``${DATA_LAKE_PATH}``:

* **Workflow A — Ingestion** (5 stages, exposed as
  ``datorcloud_ingestion_job``):

      device / sensor data
        → ``upload_datasets``      (Object Store / MinIO)
        → ``generate_metadata``    (Metadata Generation — L2 sensor metadata)
        → ``generate_metadata``    (NoSQL Metadata Store — L2/L3 + L4 cards)
        → ``catalog_update``       (Database Catalog — L1 Experiment Card +
                                    L4 Dataset Card in DuckDB)

* **Workflow B — Query & Fetch** (5 stages, exposed as
  ``datorcloud_query_fetch_job``):

      filter specification (op config)
        → ``query_metadata``       (DuckDB over L1–L4)
        → ``query_metadata``       (Matched Metadata Records — count + preview)
        → ``retrieve_objects``     (Object Retrieval from MinIO)
        → ``retrieve_objects``     (Local Filesystem Export to RETRIEVED_DATA_PATH)

Both jobs share a single :class:`DatorCloudResource`, which reads every
connection setting from the project ``.env``. No credentials are hard-coded.

Load with the Dagster CLI:

    dagster dev -f examples/datorcloud_dagster_workflow.py

or, when running this file directly, the ``__main__`` block executes both
workflows sequentially in-process and prints the status of each.
"""

import os
import tempfile
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from dagster import (
    AssetIn,
    AssetSelection,
    Config,
    DagsterInstance,
    Definitions,
    FilesystemIOManager,
    MetadataValue,
    Output,
    asset,
    define_asset_job,
)

from datorcloud.dagster import (
    DatorCloudResource,
    component_assets,
    generate_metadata,
    query_metadata,
    retrieve_objects,
    upload_datasets,
)


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------


def _env(name: str, default: str) -> str:
    """Return ``$name`` or ``default`` when the variable is unset/empty."""
    value = os.environ.get(name)
    return value if value else default


DATA_LAKE_PATH = _env("DATA_LAKE_PATH", "./dataspaces/data_lake")
RETRIEVED_DATA_PATH = _env("RETRIEVED_DATA_PATH", "./dataspaces/retrieved_data")
DATA_BUCKET = _env("DATA_BUCKET", "orx-datalake")
METADATA_BUCKET = _env("METADATA_BUCKET", "orx-metadata")

DATASET_NAME = "4dor-dataset"
METADATA_FILENAME = "metadata_4dor.csv"
METADATA_S3_PATH = f"s3://{METADATA_BUCKET}/{METADATA_FILENAME}"


# ---------------------------------------------------------------------------
# Workflow A · Stage 5/5 — Database Catalog Update (L1 + L4 in DuckDB)
# ---------------------------------------------------------------------------


class CatalogUpdateConfig(Config):
    """Configuration for the ``catalog_update`` asset.

    Refreshes the L1 Experiment Card and L4 Dataset Card tables in DuckDB
    from the metadata CSV produced by ``generate_metadata``. When
    ``metadata_file`` is omitted, the asset falls back to the upstream
    asset's ``output_file``.
    """

    metadata_file: Optional[str] = None


@asset(ins={"metadata_info": AssetIn("generate_metadata")})
def catalog_update(
    config: CatalogUpdateConfig,
    datorcloud: DatorCloudResource,
    metadata_info: Dict[str, Any],
) -> Output[Dict[str, Any]]:
    """Workflow A · Stage 5/5 — register L1 Experiment Card + L4 Dataset Card.

    Materialises two DuckDB tables that summarise the metadata CSV:

    * ``experiment_card`` — one row per ``(dataset, experiment)``: the
      L1 Experiment Card.
    * ``dataset_card`` — one row per ``dataset``: the L4 Dataset Card
      (dataset composition summary).

    Row counts are emitted as Dagster metadata so the UI surfaces a visible
    confirmation of the catalog refresh.
    """
    metadata_file = config.metadata_file or metadata_info["output_file"]
    sql_path = metadata_file.replace("\\", "/")

    query = datorcloud.query
    query.conn.execute(
        f"""
        CREATE OR REPLACE TABLE experiment_card AS
        SELECT
            dataset,
            experiment,
            COUNT(*)                       AS file_count,
            COUNT(DISTINCT camera_id)      AS sensor_count,
            COUNT(DISTINCT image_type)     AS modality_count
        FROM read_csv_auto('{sql_path}')
        GROUP BY dataset, experiment
        """
    )
    query.conn.execute(
        f"""
        CREATE OR REPLACE TABLE dataset_card AS
        SELECT
            dataset,
            COUNT(DISTINCT experiment)     AS experiment_count,
            COUNT(*)                       AS file_count,
            COUNT(DISTINCT camera_id)      AS sensor_count
        FROM read_csv_auto('{sql_path}')
        GROUP BY dataset
        """
    )
    n_exp = query.conn.execute("SELECT COUNT(*) FROM experiment_card").fetchone()[0]
    n_ds = query.conn.execute("SELECT COUNT(*) FROM dataset_card").fetchone()[0]

    payload = {
        "experiment_card_rows": int(n_exp),
        "dataset_card_rows": int(n_ds),
        "metadata_file": metadata_file,
    }
    return Output(
        payload,
        metadata={
            "experiment_card_rows": MetadataValue.int(int(n_exp)),
            "dataset_card_rows": MetadataValue.int(int(n_ds)),
            "metadata_file": MetadataValue.text(metadata_file),
        },
    )


# ---------------------------------------------------------------------------
# Resource + asset registry
# ---------------------------------------------------------------------------


datorcloud_resource = DatorCloudResource(
    data_bucket=DATA_BUCKET,
    metadata_bucket=METADATA_BUCKET,
)

all_assets = list(component_assets) + [catalog_update]


# ---------------------------------------------------------------------------
# Run configs — built once at module load so the same values can pre-fill
# the Dagster launchpad and feed ``execute_in_process`` in ``__main__``.
# ---------------------------------------------------------------------------


def _build_ingestion_run_config() -> Dict[str, Any]:
    """Run config for ``datorcloud_ingestion_job`` (Workflow A)."""
    dataset_path = os.path.join(DATA_LAKE_PATH, DATASET_NAME)
    metadata_csv = os.path.join(DATA_LAKE_PATH, METADATA_FILENAME)
    return {
        "ops": {
            "upload_datasets": {
                "config": {
                    # Stage 1/5 + 2/5 — device/sensor data → Object Store (MinIO)
                    "dataset_paths": {DATASET_NAME: dataset_path},
                    "bucket_name": DATA_BUCKET,
                }
            },
            "generate_metadata": {
                "config": {
                    # Stage 3/5 — Metadata Generation (L2 sensor metadata)
                    "dataset_dirs": {DATASET_NAME: dataset_path},
                    # Stage 4/5 — NoSQL Metadata Store (L2/L3 + L4 cards)
                    "output_file": metadata_csv,
                    "bucket_name": METADATA_BUCKET,
                    "object_name": METADATA_FILENAME,
                }
            },
            "catalog_update": {
                "config": {
                    # Stage 5/5 — Database Catalog Update (L1 + L4 in DuckDB)
                    "metadata_file": metadata_csv,
                }
            },
        }
    }


def _build_query_fetch_run_config() -> Dict[str, Any]:
    """Run config for ``datorcloud_query_fetch_job`` (Workflow B)."""
    return {
        "ops": {
            "query_metadata": {
                "config": {
                    # Stage 1/5 — Filter specification
                    "filters": {
                        "camera_id": "camera01",
                        "image_type": "colorimage",
                    },
                    # Stage 2/5 — QueryComponent (DuckDB over L1–L4)
                    "metadata_file": METADATA_S3_PATH,
                    "limit": 10,
                }
            },
            "retrieve_objects": {
                "config": {
                    # Stage 4/5 + 5/5 — Object Retrieval + Local Filesystem Export
                    "dataset": DATASET_NAME,
                    "filters": {
                        "camera_id": "camera01",
                        "image_type": "colorimage",
                    },
                    "max_files": 5,
                    "metadata_file": METADATA_S3_PATH,
                }
            },
        }
    }


INGESTION_RUN_CONFIG = _build_ingestion_run_config()
QUERY_FETCH_RUN_CONFIG = _build_query_fetch_run_config()


# ---------------------------------------------------------------------------
# Two asset jobs — one per operational workflow
# ---------------------------------------------------------------------------


datorcloud_ingestion_job = define_asset_job(
    name="datorcloud_ingestion_job",
    description=(
        "Workflow A — Ingestion. Materialises the 5-stage ingestion pipeline "
        "from the architecture diagram: device/sensor data → Object Store "
        "(MinIO) → Metadata Generation (L2) → NoSQL Metadata Store (L2/L3 + "
        "L4 cards) → Database Catalog Update (L1 Experiment Card + L4 "
        "Dataset Card)."
    ),
    selection=AssetSelection.assets(
        upload_datasets,
        generate_metadata,
        catalog_update,
    ),
    # Pre-fill the launchpad so the UI's "Materialize" button works without
    # the user pasting any YAML.
    config=INGESTION_RUN_CONFIG,
)


datorcloud_query_fetch_job = define_asset_job(
    name="datorcloud_query_fetch_job",
    description=(
        "Workflow B — Query & Fetch. Materialises the 5-stage query pipeline "
        "from the architecture diagram: filter spec → QueryComponent (DuckDB "
        "over L1–L4) → Matched Metadata Records → Object Retrieval → Local "
        "Filesystem Export. Requires Workflow A to have produced the "
        "upstream metadata CSV first."
    ),
    selection=AssetSelection.assets(
        query_metadata,
        retrieve_objects,
    ),
    config=QUERY_FETCH_RUN_CONFIG,
)


# A FilesystemIOManager is bound at the Definitions level so asset outputs
# produced by Workflow A survive across the second ``execute_in_process``
# call in the ``__main__`` block (and across UI runs of either job).
_IO_BASE_DIR = _env(
    "DATORCLOUD_DAGSTER_IO_DIR",
    os.path.join(tempfile.gettempdir(), "datorcloud_dagster_io"),
)


defs = Definitions(
    assets=all_assets,
    jobs=[datorcloud_ingestion_job, datorcloud_query_fetch_job],
    resources={
        "datorcloud": datorcloud_resource,
        "io_manager": FilesystemIOManager(base_dir=_IO_BASE_DIR),
    },
)


# ---------------------------------------------------------------------------
# Entry point — run both workflows sequentially in-process
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # ``define_asset_job`` returns an ``UnresolvedAssetJobDefinition``; the
    # callable ``execute_in_process`` only exists on the *resolved* job that
    # Definitions builds with its bound resources. ``get_job_def`` is the
    # cross-version API for that lookup (Dagster ≥ 1.11 also exposes
    # ``resolve_job_def``; we stick to the older name for compatibility).
    ingestion_job = defs.get_job_def("datorcloud_ingestion_job")
    query_fetch_job = defs.get_job_def("datorcloud_query_fetch_job")

    # A single ephemeral instance is shared between the two runs so the
    # second job can resolve the first job's upstream materialisations via
    # the FilesystemIOManager declared in Definitions.resources above.
    instance = DagsterInstance.ephemeral()

    print("=== Workflow A — Ingestion ===")
    ingestion_result = ingestion_job.execute_in_process(instance=instance)
    print(
        f"Workflow A — Ingestion:    "
        f"{'success' if ingestion_result.success else 'FAILED'}"
    )

    print("\n=== Workflow B — Query & Fetch ===")
    query_fetch_result = query_fetch_job.execute_in_process(instance=instance)
    print(
        f"Workflow B — Query & Fetch: "
        f"{'success' if query_fetch_result.success else 'FAILED'}"
    )
