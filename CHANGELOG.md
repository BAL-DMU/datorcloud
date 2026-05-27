# Changelog

All notable changes to **datorcloud** are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the version numbers follow [Semantic Versioning](https://semver.org).

## [0.2.0] - 2026-05-27

Phase 1 of the DORIS integration plan landed: the layered L1-L4 catalog,
the formal `(I, C, Q, F)` operators, and the L4 snapshot freeze.

### Added

- **L1-L4 catalog DDL** (`datorcloud/schemas/l1_l4.sql`,
  `schema_version: 1.0.0`). Idempotent. L1 unique key includes
  `study_id` so DICOM rows with multiple studies per subject do not
  collide. L2 is keyed on `(record_uid, modality, sequence)` so
  compound CVPR modality strings split losslessly. New ENUMs:
  `privacy_class`, `annotation_kind`, `instance_label`,
  `processing_stage`. New L1 companion tables: `l1_citations`,
  `l1_processing` (CVPR ingest provenance, `cvpr_folder` column on
  `l1_experiment`). New L4 tables: `l4_cohort_snapshot` (with
  `l13_payload` Parquet blob + `catalog_sha256` + `hf_publication_log`
  reserved for Phase 3) and `l4_eval_set` (annotator columns, target
  labels, inter-observer quantiles; per design invariant I3 multiple
  eval sets may reference one snapshot).
- **`datorcloud.schemas.Migration`** runner with a stable
  `schema_sha` digest computed from the canonical DDL text. Apply is
  idempotent (`schema_sha` stable across two runs).
- **`ParquetCatalogComponent`** (`datorcloud/components/parquet_catalog_component.py`),
  replacing `metadata_storage_component.py`. Hive-partitioned by
  `dataset_id` + `dataset_version` for L1-L3 layers under
  `<base>/<layer>/dataset_id=<id>/dataset_version=<v>/part.parquet`,
  flat layout for L4 tables. Canonical views `v_doris` and
  `v_doris_egress` (license / privacy filtered) materialised at
  construction.
- **Formal `(I, C, Q, F)` operators on `DatorCloudOrchestrator`** -
  `ingest(layer, df)`, `query(sql=...)` or
  `query(view=..., filters=...)`, `snapshot_cohort(...)`,
  `create_eval_set(...)`, `fetch(snapshot_id, dest)`. `from_env()`
  factory and `.env` contract unchanged; new optional
  `DATORCLOUD_CATALOG_URI` env var picks the catalog root.
- **L4 snapshot freeze** (`datorcloud/snapshots.py`). At
  `snapshot_cohort()` time, the matched L1-L3 rows are deep-copied into
  a single Parquet blob, hashed over a deterministic canonical
  serialisation into `catalog_sha256`, and persisted. The hash is stable
  across reruns even after `l2_sensor.converted_uri` is updated between
  two consecutive snapshots (the gate that integration-test
  `doris-it-01-catalog` assertion (c) checks).
- **CLI verb** `datorcloud query --sql "SELECT ... FROM v_doris"` runs
  end-to-end against the new L1-L4 catalog without MinIO credentials.
- **Integration test** `tests/integration/test_01_catalog.py`
  (`doris-it-01-catalog`) covering assertions (a)-(f) of
  STEP_BY_STEP_PLAN.md §3.

### Changed

- `DatorCloudOrchestrator.__init__` now accepts an optional
  `parquet_catalog=` and `catalog_base_uri=` argument. Existing
  callers continue to work unchanged; the new path is opt-in.
- `pyproject.toml` declares `pyarrow>=14` as a runtime dependency
  (used by the snapshot freeze) and adds package-data for
  `datorcloud.schemas/*.sql`.

### Documentation

- `docs/snapshots.md` describes the snapshot-freeze semantics, the
  canonical-serialisation hashing rule, and the L4 eval-set join
  surface that the T2D inter-observer pipeline reads in Phase 5.

### Migration notes (downstream)

- Downstream pins to `datorcloud>=0.2.0`. `msk-ai-trust-to-deploy`
  bumped its requirement in `pyproject.toml`.
- The legacy `metadata_storage_component` remains importable but is
  superseded by `ParquetCatalogComponent` for any new code path. It
  will be removed no earlier than `0.3.0`.

## [0.1.0] - 2026-05-15

- Initial public release: component-oriented framework for MinIO
  object storage, DuckDB-backed CSV queries, and Dagster assets.
