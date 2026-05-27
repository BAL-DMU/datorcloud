"""Phase 1 step 1.2 gate: ``ParquetCatalogComponent`` end-to-end behaviour.

Asserts:
  * the DDL is applied on construction,
  * ``v_doris`` and ``v_doris_egress`` views exist and respect the
    license / privacy filter,
  * round-trip writes land in the in-memory tables,
  * ``materialize_parquet`` produces the hive layout
    ``<base>/<layer>/dataset_id=<id>/dataset_version=<v>/part.parquet``
    for L1-L3 layers and a flat file for L4 layers,
  * the materialised files can be queried via ``read_parquet``
    with hive partitioning.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from datorcloud.components.parquet_catalog_component import (
    ParquetCatalogComponent,
    HIVE_PARTITIONED_LAYERS,
)


def _sample_l1(record_uid: str = "u1", privacy: str = "public") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_uid": record_uid,
                "dataset_id": "totalsegmentator",
                "dataset_version": "v2",
                "subject_id": f"s{record_uid}",
                "study_id": "",
                "privacy_class": privacy,
                "license_spdx": "CC-BY-4.0",
                "redistribution_ok": True,
                "license_rule_version": "v1",
                "share_alike_obligation": False,
            }
        ]
    )


def _sample_l2(record_uid: str = "u1", sequence: str = "") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_uid": record_uid,
                "modality": "CT",
                "sequence": sequence,
                "raw_format": "nii.gz",
                "raw_uri": f"s3://orx-datalake/totalsegmentator/{record_uid}/ct.nii.gz",
            }
        ]
    )


def _sample_l3(record_uid: str = "u1", label: str = "femur_left") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_uid": record_uid,
                "label_canonical": label,
                "annotator": "ts_v2",
                "annotation_kind": "auto",
                "instance_label": "semantic",
                "mask_uri": f"s3://orx-datalake/totalsegmentator/{record_uid}/seg/{label}.nii.gz",
            }
        ]
    )


@pytest.fixture
def catalog(tmp_path) -> ParquetCatalogComponent:
    return ParquetCatalogComponent(metadata_base_uri=str(tmp_path / "catalog"))


# ---------------------------------------------------------------------------
# Construction / DDL surface
# ---------------------------------------------------------------------------


def test_ddl_applied_on_construction(catalog: ParquetCatalogComponent) -> None:
    rows = catalog.conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    for layer in ("l1_experiment", "l2_sensor", "l3_annotation", "l4_cohort_snapshot"):
        assert layer in table_names


def test_views_exist(catalog: ParquetCatalogComponent) -> None:
    views = {
        r[0]
        for r in catalog.conn.execute(
            "SELECT table_name FROM information_schema.views"
        ).fetchall()
    }
    assert "v_doris" in views
    assert "v_doris_egress" in views


def test_schema_sha_set(catalog: ParquetCatalogComponent) -> None:
    assert catalog.schema_sha
    assert len(catalog.schema_sha) == 64


# ---------------------------------------------------------------------------
# Write / query round-trip
# ---------------------------------------------------------------------------


def test_write_rows_round_trip(catalog: ParquetCatalogComponent) -> None:
    catalog.write_rows("l1_experiment", _sample_l1())
    catalog.write_rows("l2_sensor", _sample_l2())
    catalog.write_rows("l3_annotation", _sample_l3())

    df = catalog.query("SELECT * FROM v_doris")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["record_uid"] == "u1"
    assert row["modality"] == "CT"
    assert "femur_left" in list(row["labels"])


def test_v_doris_egress_filters_dua(catalog: ParquetCatalogComponent) -> None:
    catalog.write_rows("l1_experiment", _sample_l1("u_public", "public"))
    dua = _sample_l1("u_dua", "dua")
    dua.loc[:, "redistribution_ok"] = False
    catalog.write_rows("l1_experiment", dua)

    public_only = catalog.query("SELECT record_uid FROM v_doris_egress")
    assert set(public_only["record_uid"]) == {"u_public"}

    everything = catalog.query("SELECT record_uid FROM v_doris")
    assert set(everything["record_uid"]) == {"u_public", "u_dua"}


def test_update_l2_converted_uri(catalog: ParquetCatalogComponent) -> None:
    catalog.write_rows("l1_experiment", _sample_l1())
    catalog.write_rows("l2_sensor", _sample_l2())
    catalog.update_l2_converted_uri(
        record_uid="u1",
        modality="CT",
        sequence="",
        converted_uri="s3://orx-datalake/totalsegmentator/u1/ct.zarr",
    )
    row = catalog.query("SELECT converted_uri FROM l2_sensor").iloc[0]
    assert row["converted_uri"].endswith("ct.zarr")


def test_write_rows_rejects_unknown_layer(catalog: ParquetCatalogComponent) -> None:
    with pytest.raises(ValueError):
        catalog.write_rows("not_a_layer", pd.DataFrame([{"x": 1}]))


# ---------------------------------------------------------------------------
# Parquet materialisation -- hive layout
# ---------------------------------------------------------------------------


def test_materialize_parquet_hive_layout(catalog: ParquetCatalogComponent, tmp_path) -> None:
    catalog.write_rows("l1_experiment", _sample_l1())
    catalog.write_rows("l2_sensor", _sample_l2())
    catalog.write_rows("l3_annotation", _sample_l3())

    out = catalog.materialize_parquet()
    for layer in ("l1_experiment", "l2_sensor", "l3_annotation"):
        assert out[layer], f"no files written for {layer}"
        path = Path(out[layer][0])
        assert "dataset_id=totalsegmentator" in path.as_posix()
        assert "dataset_version=v2" in path.as_posix()
        assert path.exists()
        assert layer in HIVE_PARTITIONED_LAYERS


def test_materialised_parquet_reads_back_with_hive_partitioning(
    catalog: ParquetCatalogComponent, tmp_path
) -> None:
    catalog.write_rows("l1_experiment", _sample_l1())
    catalog.materialize_parquet()

    # The hive layout must round-trip through a fresh DuckDB session
    # using read_parquet(..., hive_partitioning=true). This is the
    # protocol the Phase 4 HF httpfs reads also rely on.
    base = Path(catalog.metadata_base_uri) / "l1_experiment"
    glob = (base / "**" / "*.parquet").as_posix()
    conn = duckdb.connect(":memory:")
    df = conn.execute(
        f"SELECT * FROM read_parquet('{glob}', hive_partitioning=true)"
    ).fetchdf()
    assert "dataset_id" in df.columns
    assert "dataset_version" in df.columns
    assert df.iloc[0]["dataset_id"] == "totalsegmentator"
    assert df.iloc[0]["dataset_version"] == "v2"


def test_l4_materialises_flat(catalog: ParquetCatalogComponent) -> None:
    # Seed an L1 row so the snapshot has something to freeze.
    catalog.write_rows("l1_experiment", _sample_l1())
    catalog.write_rows("l2_sensor", _sample_l2())
    from datorcloud.snapshots import snapshot_cohort

    snapshot_cohort(catalog, dataset_id="totalsegmentator", snapshot_date="2026-05-27")

    out = catalog.materialize_parquet(layers=["l4_cohort_snapshot"])
    assert out["l4_cohort_snapshot"]
    path = Path(out["l4_cohort_snapshot"][0])
    assert "dataset_id=" not in path.as_posix()
    assert path.name == "part.parquet"
