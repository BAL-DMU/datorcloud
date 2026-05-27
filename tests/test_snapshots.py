"""Phase 1 step 1.4 gate: L4 snapshot freeze.

Asserts:
  * ``snapshot_cohort`` writes one row to ``l4_cohort_snapshot``,
  * ``catalog_sha256`` is byte-identical across two consecutive
    snapshots of the same cohort **even after**
    ``l2_sensor.converted_uri`` mutates between the two snapshots,
  * ``load_snapshot_payload`` reconstructs the frozen rows.

This is the property that integration-test ``doris-it-01-catalog``
assertion (c) exercises at the system level.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datorcloud.components.parquet_catalog_component import ParquetCatalogComponent
from datorcloud.snapshots import (
    create_eval_set,
    load_snapshot_payload,
    snapshot_cohort,
)


@pytest.fixture
def catalog(tmp_path) -> ParquetCatalogComponent:
    return ParquetCatalogComponent(metadata_base_uri=str(tmp_path / "catalog"))


def _seed_two_subjects(catalog: ParquetCatalogComponent) -> None:
    l1 = pd.DataFrame(
        [
            {
                "record_uid": "u1",
                "dataset_id": "totalsegmentator",
                "dataset_version": "v2",
                "subject_id": "s0011",
                "study_id": "",
                "privacy_class": "public",
                "license_spdx": "CC-BY-4.0",
                "redistribution_ok": True,
                "license_rule_version": "v1",
                "share_alike_obligation": False,
            },
            {
                "record_uid": "u2",
                "dataset_id": "totalsegmentator",
                "dataset_version": "v2",
                "subject_id": "s0012",
                "study_id": "",
                "privacy_class": "public",
                "license_spdx": "CC-BY-4.0",
                "redistribution_ok": True,
                "license_rule_version": "v1",
                "share_alike_obligation": False,
            },
        ]
    )
    l2 = pd.DataFrame(
        [
            {
                "record_uid": "u1",
                "modality": "CT",
                "sequence": "",
                "raw_format": "nii.gz",
                "raw_uri": "s3://orx-datalake/totalsegmentator/u1/ct.nii.gz",
            },
            {
                "record_uid": "u2",
                "modality": "CT",
                "sequence": "",
                "raw_format": "nii.gz",
                "raw_uri": "s3://orx-datalake/totalsegmentator/u2/ct.nii.gz",
            },
        ]
    )
    l3 = pd.DataFrame(
        [
            {
                "record_uid": "u1",
                "label_canonical": "femur_left",
                "annotator": "ts_v2",
                "annotation_kind": "auto",
                "instance_label": "semantic",
                "mask_uri": "s3://orx-datalake/totalsegmentator/u1/seg/femur_left.nii.gz",
            },
            {
                "record_uid": "u2",
                "label_canonical": "femur_left",
                "annotator": "ts_v2",
                "annotation_kind": "auto",
                "instance_label": "semantic",
                "mask_uri": "s3://orx-datalake/totalsegmentator/u2/seg/femur_left.nii.gz",
            },
        ]
    )
    catalog.write_rows("l1_experiment", l1)
    catalog.write_rows("l2_sensor", l2)
    catalog.write_rows("l3_annotation", l3)


# ---------------------------------------------------------------------------
# Freeze semantics
# ---------------------------------------------------------------------------


def test_snapshot_writes_row(catalog: ParquetCatalogComponent) -> None:
    _seed_two_subjects(catalog)
    snap = snapshot_cohort(
        catalog,
        dataset_id="totalsegmentator",
        snapshot_date="2026-05-27",
    )
    assert snap.snapshot_id == "totalsegmentator@2026-05-27"
    assert snap.n_records == 2
    assert len(snap.catalog_sha256) == 64

    row = catalog.query(
        "SELECT * FROM l4_cohort_snapshot WHERE snapshot_id = ?",
        params=[snap.snapshot_id],
    )
    assert len(row) == 1
    assert row.iloc[0]["n_records"] == 2
    assert row.iloc[0]["catalog_sha256"] == snap.catalog_sha256


def test_snapshot_sha_stable_across_reruns(catalog: ParquetCatalogComponent) -> None:
    _seed_two_subjects(catalog)
    a = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )
    b = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )
    assert a.catalog_sha256 == b.catalog_sha256
    assert a.n_records == b.n_records


def test_snapshot_sha_stable_after_converted_uri_writes(
    catalog: ParquetCatalogComponent,
) -> None:
    """Phase 1 §3 step 1.4 + integration-test assertion (c).

    A snapshot's ``catalog_sha256`` must remain identical even after
    asynchronous writes to ``l2_sensor.converted_uri`` between two
    consecutive snapshots of the same cohort.
    """
    _seed_two_subjects(catalog)
    first = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )

    # Simulate the conversion stage filling in converted_uri for both
    # subjects after the first snapshot was frozen.
    for uid in ("u1", "u2"):
        catalog.update_l2_converted_uri(
            record_uid=uid,
            modality="CT",
            sequence="",
            converted_uri=f"s3://orx-datalake/totalsegmentator/{uid}/ct.zarr",
        )

    second = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )
    assert first.catalog_sha256 == second.catalog_sha256, (
        "snapshot hash must be insensitive to asynchronous converted_uri "
        "writes (Phase 1 §3 step 1.4)"
    )


def test_snapshot_predicate_filters_rows(catalog: ParquetCatalogComponent) -> None:
    _seed_two_subjects(catalog)
    snap = snapshot_cohort(
        catalog,
        dataset_id="totalsegmentator",
        predicate_sql="subject_id = 's0011'",
        snapshot_date="2026-05-27",
    )
    assert snap.n_records == 1
    payload = load_snapshot_payload(catalog, snap.snapshot_id)
    l1_rows = payload[payload["layer"] == "l1_experiment"]
    assert list(l1_rows["subject_id"]) == ["s0011"]


def test_load_snapshot_payload_round_trip(catalog: ParquetCatalogComponent) -> None:
    _seed_two_subjects(catalog)
    snap = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )
    payload = load_snapshot_payload(catalog, snap.snapshot_id)
    assert {"l1_experiment", "l2_sensor", "l3_annotation"} <= set(payload["layer"])
    assert set(payload[payload["layer"] == "l1_experiment"]["record_uid"]) == {"u1", "u2"}


def test_load_snapshot_payload_missing(catalog: ParquetCatalogComponent) -> None:
    with pytest.raises(KeyError):
        load_snapshot_payload(catalog, "nonexistent@2026-05-27")


# ---------------------------------------------------------------------------
# Eval-set creation (Phase 1 step 1.5)
# ---------------------------------------------------------------------------


def test_create_eval_set_attaches(catalog: ParquetCatalogComponent) -> None:
    _seed_two_subjects(catalog)
    snap = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )
    es = create_eval_set(
        catalog,
        eval_set_id="shoulder_ct_v3",
        snapshot_id=snap.snapshot_id,
        annotator_columns=["annotator_a", "annotator_b"],
        target_labels=["femur_left", "femur_right"],
        inter_observer_quantiles=[0.25, 0.75],
    )
    assert es.eval_set_id == "shoulder_ct_v3"
    rows = catalog.query("SELECT * FROM l4_eval_set")
    assert len(rows) == 1


def test_create_eval_set_unknown_snapshot_raises(catalog: ParquetCatalogComponent) -> None:
    with pytest.raises(KeyError):
        create_eval_set(
            catalog,
            eval_set_id="x",
            snapshot_id="nonexistent@2026-05-27",
            annotator_columns=["a"],
            target_labels=["femur_left"],
        )


def test_create_eval_set_validates_quantile_arity(
    catalog: ParquetCatalogComponent,
) -> None:
    _seed_two_subjects(catalog)
    snap = snapshot_cohort(
        catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27"
    )
    with pytest.raises(ValueError):
        create_eval_set(
            catalog,
            eval_set_id="bad",
            snapshot_id=snap.snapshot_id,
            annotator_columns=["a"],
            target_labels=["femur_left"],
            inter_observer_quantiles=[0.5],  # only one value, not two
        )
