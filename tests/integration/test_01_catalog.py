"""``doris-it-01-catalog`` -- Phase 1 integration test.

Per STEP_BY_STEP_PLAN.md §3 the test runs the full
``ingest -> query -> snapshot -> fetch -> eval_set`` path against a
synthetic 5-subject TotalSegmentator v2 slice (``it_ts_5subj``). It is
the system-level proof that:

  (a) the DDL migration is idempotent (``schema_sha`` stable across two
      runs),
  (b) ``count(*) FROM l1_experiment WHERE dataset_id = 'totalsegmentator'``
      equals 5 after ingest,
  (c) the snapshot's ``catalog_sha256`` is identical on rerun, even after
      ``l2_sensor.converted_uri`` is filled in between,
  (d) ``fetch(snapshot_id=...)`` writes a byte-identical MIRO manifest on
      rerun,
  (e) two ``l4_eval_set`` rows pointing to the same ``snapshot_id`` are
      legal,
  (f) the ``Q`` operator returns the same rows whether queried through
      raw DuckDB SQL or the wrapper API.

This test runs entirely in-process: DuckDB in-memory, the parquet
catalog rooted at ``tmp_path``, no MinIO, no GPU. The Phase 1 budget is
under 60 seconds; on a stock laptop it completes in well under one.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from datorcloud.components.parquet_catalog_component import ParquetCatalogComponent
from datorcloud.core import DatorCloudOrchestrator
from datorcloud.schemas import Migration
from datorcloud.snapshots import (
    create_eval_set,
    load_snapshot_payload,
    snapshot_cohort,
)

pytestmark = pytest.mark.integration

DATASET_ID = "totalsegmentator"
DATASET_VERSION = "v2"
SNAPSHOT_DATE = "2026-05-27"


# ---------------------------------------------------------------------------
# 5-subject TS slice fixture
# ---------------------------------------------------------------------------


def _it_ts_5subj() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Synthetic stand-in for the on-disk ``it_ts_5subj`` fixture.

    Five TS-v2 subjects with one CT volume each and two annotated
    structures (``femur_left`` / ``femur_right``). Designed to validate
    every assertion in the test plan without touching the network.
    """
    subjects = [f"s{1000 + i:04d}" for i in range(5)]

    l1 = pd.DataFrame(
        [
            {
                "record_uid": f"u_{sid}",
                "dataset_id": DATASET_ID,
                "dataset_version": DATASET_VERSION,
                "subject_id": sid,
                "study_id": "",
                "cvpr_folder": None,
                "body_part": ["pelvis"] if i % 2 == 0 else ["abdomen"],
                "privacy_class": "public",
                "license_spdx": "CC-BY-4.0",
                "license_rule_version": "v1",
                "redistribution_ok": True,
                "hf_repo": "bal-dmu/msk-imaging",
                "share_alike_obligation": False,
                "source_doi": "10.5281/zenodo.10047292",
                "source_url": "https://zenodo.org/record/10047292",
            }
            for i, sid in enumerate(subjects)
        ]
    )

    l2 = pd.DataFrame(
        [
            {
                "record_uid": f"u_{sid}",
                "modality": "CT",
                "sequence": "",
                "raw_format": "nii.gz",
                "raw_uri": f"s3://orx-datalake/{DATASET_ID}/{sid}/ct.nii.gz",
                "voxel_spacing_mm": [1.5, 1.5, 1.5],
                "slice_thickness_mm": 1.5,
            }
            for sid in subjects
        ]
    )

    l3 = pd.DataFrame(
        [
            {
                "record_uid": f"u_{sid}",
                "label_canonical": label,
                "annotator": "ts_v2",
                "annotation_kind": "auto",
                "instance_label": "semantic",
                "mask_uri": f"s3://orx-datalake/{DATASET_ID}/{sid}/seg/{label}.nii.gz",
            }
            for sid in subjects
            for label in ("femur_left", "femur_right")
        ]
    )

    return l1, l2, l3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator(tmp_path) -> DatorCloudOrchestrator:
    """A catalog-only orchestrator (no MinIO / no httpfs S3 in this path)."""
    catalog = ParquetCatalogComponent(metadata_base_uri=str(tmp_path / "catalog"))
    from datorcloud.components.minio_component import MinioObjectComponent
    from datorcloud.components.query_component import QueryComponent

    class _NoopClient:
        def bucket_exists(self, bucket): return True
        def make_bucket(self, bucket): return None
        def fput_object(self, *a, **kw): return None
        def fget_object(self, *a, **kw): return None

    minio = MinioObjectComponent(client=_NoopClient())
    # QueryComponent built around the same DuckDB connection so the
    # legacy (Q) path and the new catalog views see the same state.
    qc = QueryComponent.__new__(QueryComponent)
    qc.conn = catalog.conn
    return DatorCloudOrchestrator(
        minio_component=minio,
        query_component=qc,
        parquet_catalog=catalog,
        local_download_dir=str(tmp_path / "out"),
    )


@pytest.fixture
def seeded_orchestrator(orchestrator: DatorCloudOrchestrator) -> DatorCloudOrchestrator:
    l1, l2, l3 = _it_ts_5subj()
    orchestrator.ingest("l1_experiment", l1)
    orchestrator.ingest("l2_sensor", l2)
    orchestrator.ingest("l3_annotation", l3)
    return orchestrator


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def test_a_ddl_migration_is_idempotent() -> None:
    """Assertion (a): ``schema_sha`` is stable across two runs."""
    conn = duckdb.connect(":memory:")
    m = Migration.from_path()
    sha1 = m.apply(conn).schema_sha
    sha2 = m.apply(conn).schema_sha
    assert sha1 == sha2


def test_b_ingest_produces_expected_l1_count(
    seeded_orchestrator: DatorCloudOrchestrator,
) -> None:
    """Assertion (b): 5 L1 rows after ingest."""
    df = seeded_orchestrator.query(
        sql=f"SELECT count(*) AS n FROM l1_experiment "
        f"WHERE dataset_id = '{DATASET_ID}'"
    )
    assert int(df.iloc[0]["n"]) == 5


def test_c_snapshot_sha_stable_across_converted_uri_writes(
    seeded_orchestrator: DatorCloudOrchestrator,
) -> None:
    """Assertion (c): catalog_sha256 unchanged after async conversion writes."""
    first = seeded_orchestrator.snapshot_cohort(
        dataset_id=DATASET_ID, snapshot_date=SNAPSHOT_DATE
    )
    # Async conversion stage updates converted_uri on every L2 row.
    for i in range(5):
        seeded_orchestrator.parquet_catalog.update_l2_converted_uri(
            record_uid=f"u_s{1000 + i:04d}",
            modality="CT",
            sequence="",
            converted_uri=f"s3://orx-datalake/{DATASET_ID}/s{1000 + i:04d}/ct.zarr",
        )
    second = seeded_orchestrator.snapshot_cohort(
        dataset_id=DATASET_ID, snapshot_date=SNAPSHOT_DATE
    )
    assert first.catalog_sha256 == second.catalog_sha256
    assert first.n_records == 5 == second.n_records


def test_d_fetch_writes_byte_identical_manifest(
    seeded_orchestrator: DatorCloudOrchestrator, tmp_path
) -> None:
    """Assertion (d): two fetches produce byte-identical MIRO manifests."""
    snap = seeded_orchestrator.snapshot_cohort(
        dataset_id=DATASET_ID, snapshot_date=SNAPSHOT_DATE
    )
    out_a = seeded_orchestrator.fetch(snapshot_id=snap.snapshot_id, dest=str(tmp_path / "fa"))
    out_b = seeded_orchestrator.fetch(snapshot_id=snap.snapshot_id, dest=str(tmp_path / "fb"))
    assert out_a["manifest_sha256"] == out_b["manifest_sha256"]
    assert out_a["catalog_sha256"] == out_b["catalog_sha256"] == snap.catalog_sha256
    assert Path(out_a["manifest_path"]).exists()
    assert Path(out_b["manifest_path"]).exists()
    assert (
        Path(out_a["manifest_path"]).read_bytes()
        == Path(out_b["manifest_path"]).read_bytes()
    )


def test_e_two_eval_sets_share_one_snapshot(
    seeded_orchestrator: DatorCloudOrchestrator,
) -> None:
    """Assertion (e): multiple eval sets per snapshot is legal."""
    snap = seeded_orchestrator.snapshot_cohort(
        dataset_id=DATASET_ID, snapshot_date=SNAPSHOT_DATE
    )
    seeded_orchestrator.create_eval_set(
        eval_set_id="es_femur",
        snapshot_id=snap.snapshot_id,
        annotator_columns=["ts_v2"],
        target_labels=["femur_left", "femur_right"],
        inter_observer_quantiles=[0.25, 0.75],
    )
    seeded_orchestrator.create_eval_set(
        eval_set_id="es_femur_left_only",
        snapshot_id=snap.snapshot_id,
        annotator_columns=["ts_v2"],
        target_labels=["femur_left"],
        inter_observer_quantiles=[0.1, 0.9],
    )
    rows = seeded_orchestrator.query(
        sql=f"SELECT eval_set_id FROM l4_eval_set WHERE snapshot_id = '{snap.snapshot_id}'"
    )
    assert set(rows["eval_set_id"]) == {"es_femur", "es_femur_left_only"}


def test_f_q_operator_matches_raw_sql(
    seeded_orchestrator: DatorCloudOrchestrator,
) -> None:
    """Assertion (f): the wrapper Q API returns the same rows as raw SQL."""
    via_wrapper = seeded_orchestrator.query(
        view="v_doris", filters={"modality": "CT"}
    )
    via_sql = seeded_orchestrator.query(
        sql="SELECT * FROM v_doris WHERE modality = 'CT'"
    )
    assert len(via_wrapper) == len(via_sql) == 5
    assert sorted(via_wrapper["record_uid"]) == sorted(via_sql["record_uid"])


def test_full_chain_summary(
    seeded_orchestrator: DatorCloudOrchestrator, tmp_path
) -> None:
    """A second pass over the same orchestrator -- ingest is idempotent,
    snapshot SHA stable, payload reconstructs."""
    l1, l2, l3 = _it_ts_5subj()
    # Re-ingest the same rows: counts must not double.
    seeded_orchestrator.ingest("l1_experiment", l1)
    seeded_orchestrator.ingest("l2_sensor", l2)
    seeded_orchestrator.ingest("l3_annotation", l3)
    df = seeded_orchestrator.query(
        sql=f"SELECT count(*) AS n FROM l1_experiment WHERE dataset_id = '{DATASET_ID}'"
    )
    assert int(df.iloc[0]["n"]) == 5

    snap = seeded_orchestrator.snapshot_cohort(
        dataset_id=DATASET_ID, snapshot_date=SNAPSHOT_DATE
    )
    payload = load_snapshot_payload(seeded_orchestrator.parquet_catalog, snap.snapshot_id)
    assert {"l1_experiment", "l2_sensor", "l3_annotation"} <= set(payload["layer"])

    fetch = seeded_orchestrator.fetch(snapshot_id=snap.snapshot_id, dest=str(tmp_path / "final"))
    assert fetch["n_records"] == 5
    assert len(fetch["records"]) == 5
