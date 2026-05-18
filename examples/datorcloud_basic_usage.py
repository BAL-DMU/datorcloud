#!/usr/bin/env python
"""DatorCloud — End-to-end example mirroring the two operational workflows.

This script walks the two pipelines documented in the DatorCloud architecture
diagram (see ``docs/03_components/architecture.md``) on the bundled
``4dor-dataset`` under ``${DATA_LAKE_PATH}``:

* **Workflow A — Ingestion** (5 stages):

    device / sensor data
      → Object Store (MinIO)
      → Metadata Generation (L2 sensor metadata)
      → NoSQL Metadata Store (L2/L3 + L4 dataset cards)
      → Database Catalog Update (L1 Experiment Card + L4 Dataset Card)

* **Workflow B — Query & Fetch** (5 stages):

    filter specification
      → QueryComponent (DuckDB) over L1–L4
      → Matched Metadata Records
      → Object Retrieval
      → Local Filesystem Export

All connection settings and storage paths are read from the project ``.env``;
no credentials are hard-coded. Missing required variables surface as a clear
``RuntimeError`` via ``_required_env``.

Run with no arguments:

    python examples/datorcloud_basic_usage.py
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import pandas as pd

from datorcloud import (
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    MinioObjectComponent,
    ObjectRetrievalComponent,
    QueryComponent,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("datorcloud.examples.basic")


# ---------------------------------------------------------------------------
# .env helpers (preserved from baseline)
# ---------------------------------------------------------------------------


def _env(name: str, default: str) -> str:
    """Return ``$name`` or ``default`` when the variable is unset/empty."""
    value = os.environ.get(name)
    return value if value else default


def _required_env(name: str) -> str:
    """Return ``$name`` or raise — used for secrets that must come from .env."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            "Add it to your .env file before running this example."
        )
    return value


def _endpoint() -> str:
    """Strip the scheme from ``S3_ENDPOINT`` (the Minio SDK wants host:port)."""
    raw = _env("S3_ENDPOINT", "minio:9090")
    return raw.replace("http://", "").replace("https://", "")


def _stage(workflow: str, index: int, total: int, title: str) -> None:
    """Emit a one-line stage banner that mirrors the architecture diagram."""
    log.info("[Workflow %s · Stage %d/%d] %s", workflow, index, total, title)


# ---------------------------------------------------------------------------
# Component wiring
# ---------------------------------------------------------------------------


Components = Tuple[
    MinioObjectComponent,
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    QueryComponent,
    ObjectRetrievalComponent,
]


def build_components(*, metadata_bucket: str, retrieved_dir: str) -> Components:
    """Assemble the five DatorCloud components from .env-driven settings."""
    s3_access_key = _required_env("S3_ACCESS_KEY")
    s3_secret_key = _required_env("S3_SECRET_KEY")

    minio = MinioObjectComponent(
        endpoint=_endpoint(),
        access_key=s3_access_key,
        secret_key=s3_secret_key,
    )
    generator = MetadataGeneratorComponent()
    storage = MetadataStorageComponent(
        minio_component=minio,
        metadata_bucket=metadata_bucket,
    )
    query = QueryComponent(
        s3_endpoint=_endpoint(),
        s3_access_key=s3_access_key,
        s3_secret_key=s3_secret_key,
    )
    retrieval = ObjectRetrievalComponent(
        minio_component=minio,
        query_component=query,
        local_base_dir=retrieved_dir,
    )
    return minio, generator, storage, query, retrieval


# ---------------------------------------------------------------------------
# Workflow A — Ingestion
# ---------------------------------------------------------------------------


def run_ingestion_workflow(
    *,
    minio: MinioObjectComponent,
    generator: MetadataGeneratorComponent,
    storage: MetadataStorageComponent,
    query: QueryComponent,
    dataset_paths: Dict[str, str],
    data_bucket: str,
    metadata_bucket: str,
    local_metadata_path: str,
    metadata_object_name: str,
) -> pd.DataFrame:
    """Workflow A — Ingestion (5 stages, mirrors the architecture diagram).

    ``device / sensor data → Object Store (MinIO) → Metadata Generation
    → NoSQL Metadata Store → Database Catalog Update``.

    Returns the L2 sensor-metadata ``DataFrame`` so the caller can chain it
    into Workflow B if desired.
    """
    log.info("=== Workflow A — Ingestion ===")

    # ------------------------------------------------------------------ 1/5
    _stage("A", 1, 5, "device / sensor data — resolving local dataset paths from .env")
    resolved: Dict[str, str] = {}
    for name, path in dataset_paths.items():
        if os.path.isdir(path):
            log.info("  ✓ %s → %s", name, path)
            resolved[name] = path
        else:
            log.warning("  ✗ %s → %s (missing on disk, skipping)", name, path)
    if not resolved:
        raise RuntimeError(
            "No dataset paths exist on disk; nothing to ingest. "
            "Place the 4dor-dataset under ${DATA_LAKE_PATH} and re-run."
        )

    # ------------------------------------------------------------------ 2/5
    _stage(
        "A", 2, 5,
        f"Object Store (MinIO) — uploading raw objects to bucket '{data_bucket}'",
    )
    minio.ensure_bucket_exists(data_bucket)
    upload_results: Dict[str, List[Dict[str, str]]] = {}
    for name, path in resolved.items():
        upload_results[name] = minio.upload_directory(
            local_directory=path,
            bucket_name=data_bucket,
            prefix=name,
        )
    uploaded = sum(
        1
        for files in upload_results.values()
        for f in files
        if f.get("status") == "success"
    )
    log.info("  → %d object(s) uploaded across %d dataset(s).", uploaded, len(resolved))

    # ------------------------------------------------------------------ 3/5
    _stage("A", 3, 5, "Metadata Generation — extracting L2 sensor metadata")
    metadata_df = generator.generate_metadata(dataset_dirs=resolved)
    n_datasets = metadata_df["dataset"].nunique() if not metadata_df.empty else 0
    log.info(
        "  → %d L2 sensor-metadata record(s) across %d dataset(s).",
        len(metadata_df), n_datasets,
    )

    # ------------------------------------------------------------------ 4/5
    _stage(
        "A", 4, 5,
        f"NoSQL Metadata Store — persisting L2/L3 + L4 to bucket '{metadata_bucket}'",
    )
    persisted = storage.store_metadata(
        metadata_df=metadata_df,
        local_file_path=local_metadata_path,
        bucket_name=metadata_bucket,
        object_name=metadata_object_name,
    )
    if persisted:
        log.info(
            "  → metadata written to %s and to s3://%s/%s",
            local_metadata_path, metadata_bucket, metadata_object_name,
        )
    else:
        log.warning(
            "  ✗ metadata was generated but the upload to '%s' reported failure.",
            metadata_bucket,
        )

    # ------------------------------------------------------------------ 5/5
    _stage(
        "A", 5, 5,
        "Database Catalog Update — registering L1 Experiment Card + L4 Dataset Card in DuckDB",
    )
    metadata_for_sql = local_metadata_path.replace("\\", "/")
    query.conn.execute(
        f"""
        CREATE OR REPLACE TABLE experiment_card AS
        SELECT
            dataset,
            experiment,
            COUNT(*)                       AS file_count,
            COUNT(DISTINCT camera_id)      AS sensor_count,
            COUNT(DISTINCT image_type)     AS modality_count
        FROM read_csv_auto('{metadata_for_sql}')
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
        FROM read_csv_auto('{metadata_for_sql}')
        GROUP BY dataset
        """
    )
    n_exp = query.conn.execute("SELECT COUNT(*) FROM experiment_card").fetchone()[0]
    n_ds = query.conn.execute("SELECT COUNT(*) FROM dataset_card").fetchone()[0]
    log.info(
        "  → DuckDB catalog refreshed: %d row(s) in experiment_card (L1), "
        "%d row(s) in dataset_card (L4).",
        n_exp, n_ds,
    )

    return metadata_df


# ---------------------------------------------------------------------------
# Workflow B — Query & Fetch
# ---------------------------------------------------------------------------


def run_query_and_fetch_workflow(
    *,
    query: QueryComponent,
    retrieval: ObjectRetrievalComponent,
    dataset: str,
    metadata_file: str,
    data_bucket: str,
    retrieved_dir: str,
    filters: Optional[Dict[str, str]] = None,
    limit: int = 10,
) -> None:
    """Workflow B — Query & Fetch (5 stages, mirrors the architecture diagram).

    ``filter specification → QueryComponent (DuckDB) over L1–L4
    → Matched Metadata Records → Object Retrieval → Local Filesystem Export``.
    """
    log.info("=== Workflow B — Query & Fetch ===")
    filters = filters if filters is not None else {"camera_id": "camera01"}

    # ------------------------------------------------------------------ 1/5
    _stage("B", 1, 5, f"Filter specification — {filters} (limit={limit})")

    # ------------------------------------------------------------------ 2/5
    _stage(
        "B", 2, 5,
        f"QueryComponent (DuckDB) — querying L1–L4 via {metadata_file}",
    )
    results = query.query_metadata(
        metadata_file=metadata_file, filters=filters, limit=limit
    )

    # ------------------------------------------------------------------ 3/5
    _stage("B", 3, 5, f"Matched Metadata Records — {len(results)} row(s)")
    if results.empty:
        log.warning("  No matching records; skipping retrieval and export stages.")
        return

    preview_cols = [
        c
        for c in ("dataset", "experiment", "camera_id", "image_type", "frame_number", "file_name")
        if c in results.columns
    ]
    log.info(
        "  preview (first %d row(s)):\n%s",
        min(5, len(results)),
        results[preview_cols].head().to_string(index=False),
    )

    # ------------------------------------------------------------------ 4/5
    experiment = results["experiment"].iloc[0]
    _stage(
        "B", 4, 5,
        f"Object Retrieval — fetching dataset '{dataset}' / experiment '{experiment}' from MinIO",
    )
    downloaded = retrieval.retrieve_experiment_data(
        metadata_file=metadata_file,
        dataset=dataset,
        experiment=experiment,
        data_bucket=data_bucket,
        **filters,
    )
    successes = [d for d in downloaded if d.get("success")]
    log.info("  → %d/%d object(s) retrieved.", len(successes), len(downloaded))

    # ------------------------------------------------------------------ 5/5
    _stage(
        "B", 5, 5,
        f"Local Filesystem Export — files materialised under {retrieved_dir}",
    )
    for d in successes[:5]:
        log.info("  · %s", d["local_path"])
    if len(successes) > 5:
        log.info("  · ... and %d more.", len(successes) - 5)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run Workflow A followed by Workflow B on the 4dor-dataset."""
    data_bucket = _env("DATA_BUCKET", "orx-datalake")
    metadata_bucket = _env("METADATA_BUCKET", "orx-metadata")
    data_lake = _env("DATA_LAKE_PATH", "./dataspaces/data_lake")
    retrieved_dir = _env("RETRIEVED_DATA_PATH", "./dataspaces/retrieved_data")

    dataset_name = "4dor-dataset"
    metadata_filename = "metadata_4dor.csv"

    dataset_paths = {dataset_name: os.path.join(data_lake, dataset_name)}
    local_metadata_path = os.path.join(data_lake, metadata_filename)
    metadata_s3_path = f"s3://{metadata_bucket}/{metadata_filename}"

    minio, generator, storage, query, retrieval = build_components(
        metadata_bucket=metadata_bucket,
        retrieved_dir=retrieved_dir,
    )

    run_ingestion_workflow(
        minio=minio,
        generator=generator,
        storage=storage,
        query=query,
        dataset_paths=dataset_paths,
        data_bucket=data_bucket,
        metadata_bucket=metadata_bucket,
        local_metadata_path=local_metadata_path,
        metadata_object_name=metadata_filename,
    )

    run_query_and_fetch_workflow(
        query=query,
        retrieval=retrieval,
        dataset=dataset_name,
        metadata_file=metadata_s3_path,
        data_bucket=data_bucket,
        retrieved_dir=retrieved_dir,
        filters={"camera_id": "camera01"},
        limit=10,
    )


if __name__ == "__main__":
    main()
