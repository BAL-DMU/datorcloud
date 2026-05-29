# Changelog

All notable changes to **datorcloud** are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the version numbers follow [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- **`doris_model_weights_sensor`** (`datorcloud/dagster/evaluation_sensor.py`) —
  Dagster sensor that enqueues a Phase-5 `run_evaluation` job whenever
  weights under `s3://doris-models/<family>/` change. Exposes
  `build_eval_run_requests()` and `weights_changed()` for unit tests.

Phase 4 of the DORIS integration plan ships entirely inside
`msk-ai-trust-to-deploy` (the DORIS consumer): a read-only HF client
(`DorisHFClient`), the cross-tier `build_cohort(source='hf')` path,
the predicate library, and the `doris cohort fetch` CLI verb. No
DatorCloud changes are required — Phase 3's `HFPublisherComponent`
already emits the catalog layout (`<hub>/catalog/{l1,l2,l3,l4_*,
v_doris}.parquet`) the new client reads. The
`LocalFilesystemHub` / `LocalFilesystemReadBackend` pair is the shared
contract between the publisher (write side) and the new client (read
side); the Phase 4 integration test in T2D rounds-trips publish → read
in one process to assert it.

See `99_integration_plan/STEP_BY_STEP_PLAN.md` §6 for the full Phase 4
deliverables and `../msk-ai-trust-to-deploy/CHANGELOG.md` for the
client-side release notes.

## [0.3.0] - 2026-05-28

Phase 3 of the DORIS integration plan landed: DatorCloud is now the
**uploader** for Hugging Face. A new `HFPublisherComponent` lifts an L4
snapshot from MinIO + the layered Parquet catalog onto a HF dataset
repo, alongside L1-L4 Parquet sidecars. The Hub becomes the queryable
public face of the same catalog the TRE keeps as the master.

### Added

- **`HFPublisherComponent`** (`datorcloud/components/hf_publisher_component.py`)
  -- the canonical egress component for Phase 3. Streams a snapshot's
  CC-BY-eligible records to a HF dataset repo and co-publishes L1-L4
  Parquet sidecars under `catalog/`. Per-subject manifests +
  (optionally) raw / converted / mask blobs land under
  `data/<dataset_id>/<subject_id>/`. The component is intentionally
  *additive*: it never mutates the source catalog beyond appending one
  entry to `l4_cohort_snapshot.hf_publication_log` after a successful
  push.
- **`HubBackend` abstraction** + two implementations:
  `LocalFilesystemHub` (offline-friendly, deterministic revision SHA
  -- used by the Phase 3 integration tests) and `HuggingFaceHub` (real
  `huggingface_hub`-backed push, selected by `doris publish
  --dry-run=false`).
- **Publish-time license gate** (per design invariant I5, defence in
  depth on top of the Phase 2 ingest gate). Raises
  `LicensePolicyError` *before* any byte is written when: an L1 row's
  `license_spdx` is outside `allowed_licenses`; a row carries
  `redistribution_ok=False`; a row carries
  `share_alike_obligation=True` for a non-SA repo (SA contamination);
  a row carries `share_alike_obligation=False` for the SA repo; or a
  row's `privacy_class` is outside `allowed_privacy` (default
  `('public',)` refuses DUA / restricted). Raises
  `CitationCompletenessError` when a DOI in `l1_citations` is missing
  from the rendered README.
- **`PublishPolicy` / `PublishResult`** dataclasses + new
  `DatorCloudOrchestrator.publish_to_hub(snapshot_id, hub_id, ...,
  dry_run=True)` entry point.
- **Dataset card template** (`datorcloud/templates/dataset_card.md.template`)
  and a layout doc (`datorcloud/templates/catalog_layout.md`) that
  external contributors mirror.
- **`hf_publication_log` write-back**: after a successful non-dry-run
  push, the result (hub_id, revision_sha, timestamp, n_files,
  catalog_sha256) is appended to `l4_cohort_snapshot.hf_publication_log`
  as a JSON array.
- **Documentation**: `docs/hf_layout.md` describes the MIRO-on-HF
  convention, the publish-time license gate, the `HubBackend`
  abstraction, and the I6 cross-tier identity invariant.
- **Integration test** `tests/test_hf_publisher.py` covering the
  publish round-trip via `LocalFilesystemHub`.

### Changed

- `pyproject.toml`: version bumped to `0.3.0`; package-data now ships
  `datorcloud.templates/*.template` + `*.md` so the dataset card lands
  in the wheel.
- `DatorCloudOrchestrator`: new `publish_to_hub` method. Existing
  `(I, C, Q, F)` operators unchanged; the new path is opt-in via the
  Phase 1 `catalog_base_uri=` argument.
- `datorcloud.__init__` now re-exports the publisher surface
  (`HFPublisherComponent`, `HubBackend`, `LocalFilesystemHub`,
  `HuggingFaceHub`, `PublishPolicy`, `PublishResult`,
  `LicensePolicyError`, `CitationCompletenessError`).

### Migration notes (downstream)

- Downstream pins to `datorcloud>=0.3.0`. The
  `msk-ai-trust-to-deploy` repo bumped its requirement in
  `pyproject.toml` and added a `doris publish` CLI verb that wraps
  this new entry point.
- The L1-L4 DDL is unchanged. `l4_cohort_snapshot.hf_publication_log`
  was reserved in 0.2.0 and is now populated by the publisher.

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
