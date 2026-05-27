"""Phase 1 step 1.5 gate: multiple eval sets reference the same snapshot.

This is design invariant I3 (snapshot ⟂ eval-set orthogonality) at the
SQL layer: the join from ``l4_eval_set`` back to its parent
``l4_cohort_snapshot`` must support an N:1 relationship.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datorcloud.components.parquet_catalog_component import ParquetCatalogComponent
from datorcloud.snapshots import create_eval_set, snapshot_cohort


@pytest.fixture
def catalog(tmp_path) -> ParquetCatalogComponent:
    return ParquetCatalogComponent(metadata_base_uri=str(tmp_path / "catalog"))


def _seed(catalog: ParquetCatalogComponent) -> str:
    catalog.write_rows(
        "l1_experiment",
        pd.DataFrame(
            [
                {
                    "record_uid": "u1",
                    "dataset_id": "ts",
                    "dataset_version": "v2",
                    "subject_id": "s1",
                    "study_id": "",
                    "privacy_class": "public",
                    "license_spdx": "CC-BY-4.0",
                    "redistribution_ok": True,
                    "license_rule_version": "v1",
                    "share_alike_obligation": False,
                }
            ]
        ),
    )
    snap = snapshot_cohort(catalog, dataset_id="ts", snapshot_date="2026-05-27")
    return snap.snapshot_id


def test_two_eval_sets_share_one_snapshot(catalog: ParquetCatalogComponent) -> None:
    sid = _seed(catalog)
    create_eval_set(
        catalog,
        eval_set_id="es_pelvis",
        snapshot_id=sid,
        annotator_columns=["radiologist_a", "radiologist_b"],
        target_labels=["femur_left"],
        inter_observer_quantiles=[0.25, 0.75],
    )
    create_eval_set(
        catalog,
        eval_set_id="es_shoulder",
        snapshot_id=sid,
        annotator_columns=["radiologist_c", "radiologist_d"],
        target_labels=["femur_right"],
        inter_observer_quantiles=[0.1, 0.9],
    )

    rows = catalog.query("SELECT eval_set_id, snapshot_id FROM l4_eval_set ORDER BY eval_set_id")
    assert len(rows) == 2
    assert set(rows["snapshot_id"]) == {sid}  # both reference the same snapshot
    assert set(rows["eval_set_id"]) == {"es_pelvis", "es_shoulder"}


def test_eval_set_join_to_snapshot(catalog: ParquetCatalogComponent) -> None:
    sid = _seed(catalog)
    create_eval_set(
        catalog,
        eval_set_id="es_a",
        snapshot_id=sid,
        annotator_columns=["a"],
        target_labels=["femur_left"],
    )
    joined = catalog.query(
        """
        SELECT es.eval_set_id, cs.snapshot_id, cs.n_records, cs.catalog_sha256
          FROM l4_eval_set es
          JOIN l4_cohort_snapshot cs USING (snapshot_id)
         ORDER BY es.eval_set_id
        """
    )
    assert len(joined) == 1
    assert joined.iloc[0]["snapshot_id"] == sid
    assert joined.iloc[0]["n_records"] == 1


def test_eval_set_rejects_unknown_snapshot(catalog: ParquetCatalogComponent) -> None:
    with pytest.raises(KeyError):
        create_eval_set(
            catalog,
            eval_set_id="orphan",
            snapshot_id="ghost@2026-05-27",
            annotator_columns=["a"],
            target_labels=["femur_left"],
        )
