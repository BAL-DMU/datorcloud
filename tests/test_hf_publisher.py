"""Tests for the Phase 3 ``HFPublisherComponent``.

Exercises the publisher round-trip via the offline
:class:`LocalFilesystemHub` backend so the test runs without network
or a real Hugging Face account. Mirrors the assertions the integration
test (`doris-it-03-hf-upload`) makes at the system level.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import duckdb
import pandas as pd
import pyarrow.parquet as pq
import pytest

from datorcloud.components.hf_publisher_component import (
    CitationCompletenessError,
    HFPublisherComponent,
    LicensePolicyError,
    LocalFilesystemHub,
    PublishPolicy,
    read_publication_log,
)
from datorcloud.components.parquet_catalog_component import ParquetCatalogComponent
from datorcloud.snapshots import snapshot_cohort

DATASET_ID = "totalsegmentator"
DATASET_VERSION = "v2"
SNAPSHOT_DATE = "2026-05-28"


# ---------------------------------------------------------------------------
# Fixtures: a small in-memory catalog with one TS-v2 slice + one VerSe slice
# ---------------------------------------------------------------------------


def _ts_l1_rows(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_uid": f"ts_u_{i}",
                "dataset_id": DATASET_ID,
                "dataset_version": DATASET_VERSION,
                "subject_id": f"ts_s{1000 + i:04d}",
                "study_id": "",
                "cvpr_folder": None,
                "body_part": ["pelvis"],
                "privacy_class": "public",
                "license_spdx": "CC-BY-4.0",
                "license_rule_version": "v1",
                "redistribution_ok": True,
                "hf_repo": "bal-dmu/msk-imaging",
                "share_alike_obligation": False,
                "source_doi": "10.5281/zenodo.10047292",
                "source_url": "https://zenodo.org/record/10047292",
            }
            for i in range(n)
        ]
    )


def _ts_l2_rows(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_uid": f"ts_u_{i}",
                "modality": "CT",
                "sequence": "",
                "raw_format": "nifti",
                "raw_uri": f"s3://orx-datalake/{DATASET_ID}/ts_s{1000 + i:04d}/ct.nii.gz",
            }
            for i in range(n)
        ]
    )


def _ts_l3_rows(n: int = 3) -> pd.DataFrame:
    rows = []
    for i in range(n):
        for label in ("femur_left", "femur_right"):
            rows.append(
                {
                    "record_uid": f"ts_u_{i}",
                    "label_canonical": label,
                    "annotator": "TS_CT_v2",
                    "annotation_kind": "manual",
                    "instance_label": "semantic",
                    "label_native": label,
                    "mask_uri": f"s3://orx-datalake/{DATASET_ID}/ts_s{1000 + i:04d}/seg/{label}.nii.gz",
                }
            )
    return pd.DataFrame(rows)


def _ts_citations(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_uid": f"ts_u_{i}",
                "doi": "10.1148/ryai.230024",
                "citation": (
                    "Wasserthal J et al. TotalSegmentator: Robust Segmentation of "
                    "104 Anatomic Structures in CT Images. Radiology AI. 2023."
                ),
            }
            for i in range(n)
        ]
    )


def _verse_rows(n: int = 2) -> Tuple[pd.DataFrame, pd.DataFrame]:
    l1 = pd.DataFrame(
        [
            {
                "record_uid": f"verse_u_{i}",
                "dataset_id": "verse",
                "dataset_version": "combined_v19_v20",
                "subject_id": f"verse_s{2000 + i:04d}",
                "study_id": "",
                "body_part": ["lumbar_spine"],
                "privacy_class": "public",
                "license_spdx": "CC-BY-SA-4.0",
                "license_rule_version": "v1",
                "redistribution_ok": True,
                "hf_repo": "bal-dmu/msk-imaging-sa",
                "share_alike_obligation": True,
                "source_url": "https://github.com/anjany/verse",
            }
            for i in range(n)
        ]
    )
    l2 = pd.DataFrame(
        [
            {
                "record_uid": f"verse_u_{i}",
                "modality": "CT",
                "sequence": "",
                "raw_format": "nifti",
                "raw_uri": f"s3://orx-datalake-sa/verse/verse_s{2000 + i:04d}/image.nii.gz",
            }
            for i in range(n)
        ]
    )
    return l1, l2


@pytest.fixture
def catalog(tmp_path) -> ParquetCatalogComponent:
    cat = ParquetCatalogComponent(metadata_base_uri=str(tmp_path / "catalog"))
    cat.write_rows("l1_experiment", _ts_l1_rows())
    cat.write_rows("l2_sensor", _ts_l2_rows())
    cat.write_rows("l3_annotation", _ts_l3_rows())
    cat.write_rows("l1_citations", _ts_citations())
    return cat


@pytest.fixture
def ts_snapshot(catalog: ParquetCatalogComponent):
    return snapshot_cohort(
        catalog,
        dataset_id=DATASET_ID,
        predicate_sql=f"dataset_id = '{DATASET_ID}'",
        snapshot_date=SNAPSHOT_DATE,
    )


@pytest.fixture
def hub(tmp_path) -> LocalFilesystemHub:
    return LocalFilesystemHub(tmp_path / "mock_hub")


# ---------------------------------------------------------------------------
# Happy-path publish (assertion a + f from doris-it-03)
# ---------------------------------------------------------------------------


def test_publish_to_hub_writes_dataset_card_and_catalog_sidecars(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    publisher = HFPublisherComponent(catalog)
    result = publisher.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub,
        dry_run=False,
    )

    files = hub.list_files("bal-dmu/msk-imaging")
    assert "README.md" in files
    for sidecar in ("l1.parquet", "l2.parquet", "l3.parquet", "v_doris.parquet", "l4_snapshots.parquet"):
        assert f"catalog/{sidecar}" in files, f"missing sidecar {sidecar}; files={files}"

    # Every TS subject manifest landed under data/.
    expected_manifests = sorted(
        f"data/{DATASET_ID}/ts_s{1000 + i:04d}/manifest.json" for i in range(3)
    )
    actual_manifests = sorted(f for f in files if f.endswith("manifest.json"))
    assert actual_manifests == expected_manifests

    # The published l1.parquet has the same row count as the snapshot payload.
    l1_bytes = hub.read_file("bal-dmu/msk-imaging", "catalog/l1.parquet")
    import io as _io

    table = pq.read_table(_io.BytesIO(l1_bytes))
    assert table.num_rows == ts_snapshot.n_records == 3

    assert result.dry_run is False
    assert result.n_records == 3
    assert result.revision_sha and len(result.revision_sha) == 64


def test_dry_run_does_not_touch_the_backend(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    publisher = HFPublisherComponent(catalog)
    result = publisher.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub,
        dry_run=True,
    )
    # The repo dir is created (ensure_repo) but no files inside.
    assert hub.list_files("bal-dmu/msk-imaging") == []
    assert result.dry_run is True
    assert result.n_files_written > 0  # files_written records what would have been pushed
    assert len(result.files_written) == result.n_files_written


# ---------------------------------------------------------------------------
# License gate (b/c)
# ---------------------------------------------------------------------------


def test_unknown_license_blocks_publish(
    catalog: ParquetCatalogComponent, hub: LocalFilesystemHub
) -> None:
    """SA / unknown licenses must refuse publish at the gate."""
    bad = _ts_l1_rows(1).iloc[[0]].copy()
    bad.loc[bad.index[0], "license_spdx"] = "LicenseRef-UNKNOWN"
    bad.loc[bad.index[0], "privacy_class"] = "restricted"
    bad.loc[bad.index[0], "redistribution_ok"] = False
    bad.loc[bad.index[0], "record_uid"] = "ts_u_bad"
    bad.loc[bad.index[0], "subject_id"] = "ts_sbad0001"
    catalog.write_rows("l1_experiment", bad)

    snap = snapshot_cohort(
        catalog,
        dataset_id=DATASET_ID,
        predicate_sql="record_uid = 'ts_u_bad'",
        snapshot_date=SNAPSHOT_DATE,
    )
    publisher = HFPublisherComponent(catalog)
    with pytest.raises(LicensePolicyError) as exc:
        publisher.publish_snapshot(
            snapshot_id=snap.snapshot_id,
            policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
            backend=hub,
            dry_run=False,
        )
    assert "LicenseRef-UNKNOWN" in str(exc.value)
    # No files written.
    assert hub.list_files("bal-dmu/msk-imaging") == []


def test_share_alike_contamination_blocks_publish_to_umbrella(
    catalog: ParquetCatalogComponent, hub: LocalFilesystemHub
) -> None:
    """A CC-BY-SA row must NOT slip into the CC-BY umbrella repo."""
    sa_l1, sa_l2 = _verse_rows(2)
    catalog.write_rows("l1_experiment", sa_l1)
    catalog.write_rows("l2_sensor", sa_l2)

    snap = snapshot_cohort(
        catalog,
        dataset_id="verse",
        predicate_sql="dataset_id = 'verse'",
        snapshot_date=SNAPSHOT_DATE,
    )

    publisher = HFPublisherComponent(catalog)
    with pytest.raises(LicensePolicyError) as exc:
        publisher.publish_snapshot(
            snapshot_id=snap.snapshot_id,
            policy=PublishPolicy(
                hub_id="bal-dmu/msk-imaging",
                allowed_licenses=("CC-BY-4.0", "CC-BY-SA-4.0"),
            ),
            backend=hub,
            dry_run=False,
        )
    assert "SA contamination" in str(exc.value)


def test_sa_repo_accepts_share_alike_rows(
    catalog: ParquetCatalogComponent, hub: LocalFilesystemHub
) -> None:
    sa_l1, sa_l2 = _verse_rows(2)
    catalog.write_rows("l1_experiment", sa_l1)
    catalog.write_rows("l2_sensor", sa_l2)
    snap = snapshot_cohort(
        catalog,
        dataset_id="verse",
        predicate_sql="dataset_id = 'verse'",
        snapshot_date=SNAPSHOT_DATE,
    )

    publisher = HFPublisherComponent(catalog)
    result = publisher.publish_snapshot(
        snapshot_id=snap.snapshot_id,
        policy=PublishPolicy(
            hub_id="bal-dmu/msk-imaging-sa",
            allowed_licenses=("CC-BY-SA-4.0",),
            require_share_alike=True,
        ),
        backend=hub,
        dry_run=False,
    )
    assert result.n_records == 2
    assert "README.md" in hub.list_files("bal-dmu/msk-imaging-sa")


def test_sa_repo_refuses_non_sa_rows(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    """TS-v2 (no SA) cannot be pushed to the SA-isolated repo."""
    publisher = HFPublisherComponent(catalog)
    with pytest.raises(LicensePolicyError) as exc:
        publisher.publish_snapshot(
            snapshot_id=ts_snapshot.snapshot_id,
            policy=PublishPolicy(
                hub_id="bal-dmu/msk-imaging-sa",
                allowed_licenses=("CC-BY-4.0", "CC-BY-SA-4.0"),
                require_share_alike=True,
            ),
            backend=hub,
            dry_run=False,
        )
    assert "share-alike" in str(exc.value).lower()


def test_dua_records_refuse_publish_by_default(
    catalog: ParquetCatalogComponent, hub: LocalFilesystemHub
) -> None:
    dua = _ts_l1_rows(1).iloc[[0]].copy()
    dua.loc[dua.index[0], "record_uid"] = "dua_u_1"
    dua.loc[dua.index[0], "subject_id"] = "dua_s1"
    dua.loc[dua.index[0], "license_spdx"] = "LicenseRef-DUA"
    dua.loc[dua.index[0], "privacy_class"] = "dua"
    dua.loc[dua.index[0], "redistribution_ok"] = False
    catalog.write_rows("l1_experiment", dua)
    snap = snapshot_cohort(
        catalog,
        dataset_id=DATASET_ID,
        predicate_sql="record_uid = 'dua_u_1'",
        snapshot_date=SNAPSHOT_DATE,
    )
    publisher = HFPublisherComponent(catalog)
    with pytest.raises(LicensePolicyError):
        publisher.publish_snapshot(
            snapshot_id=snap.snapshot_id,
            policy=PublishPolicy(
                hub_id="bal-dmu/msk-imaging",
                allowed_licenses=("CC-BY-4.0", "LicenseRef-DUA"),
            ),
            backend=hub,
            dry_run=False,
        )


# ---------------------------------------------------------------------------
# Metadata-only repo (VISCERAL)
# ---------------------------------------------------------------------------


def test_metadata_only_repo_emits_no_data_blobs(
    catalog: ParquetCatalogComponent, hub: LocalFilesystemHub
) -> None:
    # VISCERAL-meta style: rows with privacy_class='dua' but the repo
    # explicitly opts in via allowed_privacy + metadata_only=True.
    visceral = _ts_l1_rows(2).copy()
    visceral.loc[:, "record_uid"] = ["visc_u_0", "visc_u_1"]
    visceral.loc[:, "subject_id"] = ["visc_s0", "visc_s1"]
    visceral.loc[:, "dataset_id"] = "visceral_gc"
    visceral.loc[:, "license_spdx"] = "LicenseRef-DUA"
    visceral.loc[:, "privacy_class"] = "dua"
    visceral.loc[:, "redistribution_ok"] = False
    catalog.write_rows("l1_experiment", visceral)

    snap = snapshot_cohort(
        catalog,
        dataset_id="visceral_gc",
        predicate_sql="dataset_id = 'visceral_gc'",
        snapshot_date=SNAPSHOT_DATE,
    )

    publisher = HFPublisherComponent(catalog)
    result = publisher.publish_snapshot(
        snapshot_id=snap.snapshot_id,
        policy=PublishPolicy(
            hub_id="bal-dmu/msk-imaging-visceral-meta",
            allowed_licenses=("LicenseRef-DUA",),
            require_redistribution_ok=False,
            require_share_alike=None,
            allowed_privacy=("public", "dua"),
            metadata_only=True,
        ),
        backend=hub,
        dry_run=False,
    )
    files = hub.list_files("bal-dmu/msk-imaging-visceral-meta")
    # No blobs under data/<dataset_id>/<subject_id>/image*.nii.gz.
    image_blobs = [f for f in files if f.endswith(".nii.gz")]
    assert image_blobs == []
    # Only L1 + L4 sidecars under catalog/.
    catalog_files = [f for f in files if f.startswith("catalog/")]
    assert sorted(catalog_files) == ["catalog/l1.parquet", "catalog/l4_snapshots.parquet"]
    assert result.n_records == 2


# ---------------------------------------------------------------------------
# Citation completeness (d)
# ---------------------------------------------------------------------------


def test_citation_completeness_required(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    """Mutate the publisher to drop the citation block; gate must fire."""
    publisher = HFPublisherComponent(catalog)

    original_render = publisher.render_dataset_card

    def _broken_render(**kwargs):
        # Render but strip every DOI from the body to force a violation.
        body = original_render(**kwargs).decode("utf-8")
        body = body.replace("10.1148/ryai.230024", "REDACTED")
        return body.encode("utf-8")

    publisher.render_dataset_card = _broken_render  # type: ignore[assignment]

    with pytest.raises(CitationCompletenessError):
        publisher.publish_snapshot(
            snapshot_id=ts_snapshot.snapshot_id,
            policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
            backend=hub,
            dry_run=False,
        )


# ---------------------------------------------------------------------------
# hf_publication_log persistence (g)
# ---------------------------------------------------------------------------


def test_hf_publication_log_appended_on_success(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    publisher = HFPublisherComponent(catalog)
    publisher.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub,
        dry_run=False,
    )
    # Second push appends.
    publisher.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub,
        dry_run=False,
    )
    log = read_publication_log(catalog, ts_snapshot.snapshot_id)
    assert len(log) == 2
    for entry in log:
        assert entry["hub_id"] == "bal-dmu/msk-imaging"
        assert len(entry["revision_sha"]) == 64
        assert entry["dry_run"] is False
        assert entry["n_records"] == 3


def test_dry_run_does_not_touch_publication_log(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    publisher = HFPublisherComponent(catalog)
    publisher.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub,
        dry_run=True,
    )
    assert read_publication_log(catalog, ts_snapshot.snapshot_id) == []


# ---------------------------------------------------------------------------
# Reproducibility (f bis): rerunning the same publish yields identical bytes
# ---------------------------------------------------------------------------


def test_publish_is_byte_deterministic(
    catalog: ParquetCatalogComponent, ts_snapshot, tmp_path
) -> None:
    hub_a = LocalFilesystemHub(tmp_path / "hub_a")
    hub_b = LocalFilesystemHub(tmp_path / "hub_b")

    publisher_a = HFPublisherComponent(catalog)
    publisher_b = HFPublisherComponent(catalog)

    result_a = publisher_a.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub_a,
        dry_run=False,
    )
    result_b = publisher_b.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub_b,
        dry_run=False,
    )

    # Each artefact must be byte-identical between the two backends.
    for path in result_a.files_written:
        assert hub_a.read_file("bal-dmu/msk-imaging", path) == hub_b.read_file(
            "bal-dmu/msk-imaging", path
        ), f"file {path} differs between publishes"
    assert result_a.revision_sha == result_b.revision_sha


# ---------------------------------------------------------------------------
# Sidecar fidelity (f from doris-it-03)
# ---------------------------------------------------------------------------


def test_published_l1_parquet_row_count_matches_snapshot_payload(
    catalog: ParquetCatalogComponent, ts_snapshot, hub: LocalFilesystemHub
) -> None:
    publisher = HFPublisherComponent(catalog)
    publisher.publish_snapshot(
        snapshot_id=ts_snapshot.snapshot_id,
        policy=PublishPolicy(hub_id="bal-dmu/msk-imaging"),
        backend=hub,
        dry_run=False,
    )

    import io as _io

    l1_bytes = hub.read_file("bal-dmu/msk-imaging", "catalog/l1.parquet")
    table = pq.read_table(_io.BytesIO(l1_bytes))
    assert table.num_rows == ts_snapshot.n_records

    # And the L4 snapshot sidecar carries the same catalog_sha256.
    l4_bytes = hub.read_file("bal-dmu/msk-imaging", "catalog/l4_snapshots.parquet")
    l4 = pq.read_table(_io.BytesIO(l4_bytes)).to_pandas()
    assert l4.iloc[0]["catalog_sha256"] == ts_snapshot.catalog_sha256
