-- =====================================================================
-- DORIS L1-L4 catalog DDL (schema_version: 1.0.0)
--
-- Upstreamed into DatorCloud in Phase 1 of the DORIS integration plan
-- (see msk-ai-trust-to-deploy/99_integration_plan/STEP_BY_STEP_PLAN.md §3).
-- This file is the single source of truth for the layered catalog that the
-- (I, C, Q, F) operators consume. Two design invariants are encoded here:
--
--   * L1 unique key includes ``study_id`` so DICOM rows with multiple
--     studies per ``subject_id`` do not collide on ingest.
--   * L2 (``l2_sensor``) is keyed by (record_uid, modality, sequence) so
--     compound CVPR modality strings (e.g. ``"MR (T2, ADC)"``) split
--     losslessly into one row per sequence -- no semicolon-delimited
--     freeform strings in the catalog ever.
--
-- The DDL is idempotent: every CREATE statement is guarded with
-- ``IF NOT EXISTS`` (DuckDB 1.2+) and is safe to re-run by the migration
-- runner in ``schemas/migrations.py``. The migration runner hashes this
-- file into ``schema_sha`` so two runs of an unchanged DDL emit identical
-- hashes (integration-test gate ``doris-it-01-catalog`` assertion (a)).
-- =====================================================================


-- ---------------------------------------------------------------------
-- Controlled vocabularies (ENUMs)
-- ---------------------------------------------------------------------

CREATE TYPE IF NOT EXISTS privacy_class AS ENUM (
    'public',
    'restricted',
    'dua'
);

CREATE TYPE IF NOT EXISTS annotation_kind AS ENUM (
    'manual',
    'semi_automated',
    'auto',
    'reference'
);

-- ``instance_label`` distinguishes segmentation kinds so a single mask
-- column can carry semantic, instance, or panoptic masks without
-- per-dataset adapters guessing at runtime.
CREATE TYPE IF NOT EXISTS instance_label AS ENUM (
    'semantic',
    'instance',
    'panoptic',
    'binary'
);

CREATE TYPE IF NOT EXISTS processing_stage AS ENUM (
    'ingested',
    'converted',
    'qc_passed',
    'failed',
    'snapshotted'
);


-- ---------------------------------------------------------------------
-- L1 - Experiment (administrative + provenance)
-- ---------------------------------------------------------------------
--
-- One row per (dataset_id, dataset_version, subject_id, study_id) tuple.
-- ``record_uid`` is the join key shared by L2 and L3. For non-DICOM rows
-- ``study_id`` defaults to '' (empty string) which preserves a single
-- row per subject; for DICOM rows the StudyInstanceUID is required to
-- split multiple visits.
CREATE TABLE IF NOT EXISTS l1_experiment (
    record_uid              VARCHAR PRIMARY KEY,
    dataset_id              VARCHAR NOT NULL,
    dataset_version         VARCHAR NOT NULL,
    subject_id              VARCHAR NOT NULL,
    study_id                VARCHAR NOT NULL DEFAULT '',
    cvpr_folder             VARCHAR,
    body_part               VARCHAR[],
    privacy_class           privacy_class NOT NULL,
    license_spdx            VARCHAR NOT NULL,
    license_rule_version    VARCHAR NOT NULL DEFAULT 'v0',
    redistribution_ok       BOOLEAN NOT NULL,
    hf_repo                 VARCHAR,
    share_alike_obligation  BOOLEAN NOT NULL DEFAULT FALSE,
    source_doi              VARCHAR,
    source_url              VARCHAR,
    ingested_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_id, dataset_version, subject_id, study_id)
);


-- ---------------------------------------------------------------------
-- L1 companion -- per-record citation list (DOIs/papers).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS l1_citations (
    record_uid VARCHAR NOT NULL,
    doi        VARCHAR NOT NULL,
    citation   VARCHAR NOT NULL,
    PRIMARY KEY (record_uid, doi)
);


-- ---------------------------------------------------------------------
-- L1 companion -- processing provenance for CVPR-style ingest.
-- ---------------------------------------------------------------------
--
-- A single record may move through multiple stages (ingested -> converted
-- -> qc_passed -> snapshotted). The table is append-only at the
-- (record_uid, stage) grain; stage transitions are observed in lineage.
CREATE TABLE IF NOT EXISTS l1_processing (
    record_uid VARCHAR NOT NULL,
    stage      processing_stage NOT NULL,
    stage_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    runner     VARCHAR,
    notes      VARCHAR,
    PRIMARY KEY (record_uid, stage)
);


-- ---------------------------------------------------------------------
-- L2 - Sensor (acquisition params + raw/converted blob URIs)
-- ---------------------------------------------------------------------
--
-- Primary key (record_uid, modality, sequence) splits compound CVPR
-- modality strings into one row per sequence: e.g. ``"MR (T2, ADC)"``
-- becomes two rows -- (record_uid, 'MR', 'T2') and (record_uid, 'MR',
-- 'ADC'). Non-sequence modalities (CT, US) carry sequence='' as a
-- non-NULL sentinel so the unique constraint applies uniformly.
--
-- ``converted_uri`` is populated asynchronously by the
-- raw->NIfTI/Zarr/etc conversion stage. Writes to it after the L4
-- snapshot freeze do NOT mutate the snapshot's ``catalog_sha256``
-- because snapshots deep-copy the L1-L3 payload at freeze time.
CREATE TABLE IF NOT EXISTS l2_sensor (
    record_uid          VARCHAR NOT NULL,
    modality            VARCHAR NOT NULL,
    sequence            VARCHAR NOT NULL DEFAULT '',
    raw_format          VARCHAR NOT NULL,
    raw_uri             VARCHAR,
    converted_format    VARCHAR,
    converted_uri       VARCHAR,
    voxel_spacing_mm    DOUBLE[],
    slice_thickness_mm  DOUBLE,
    field_strength_t    DOUBLE,
    scanner_model       VARCHAR,
    PRIMARY KEY (record_uid, modality, sequence)
);


-- ---------------------------------------------------------------------
-- L3 - Annotation (per-label, per-annotator)
-- ---------------------------------------------------------------------
--
-- Multi-annotator support is built-in: the same (record_uid,
-- label_canonical) pair may appear under multiple ``annotator`` values.
-- ``label_canonical`` MUST resolve in config/msk_label_map.yaml (Phase 0
-- gate); ``label_native`` preserves the adapter's raw string for audit.
CREATE TABLE IF NOT EXISTS l3_annotation (
    record_uid         VARCHAR NOT NULL,
    label_canonical    VARCHAR NOT NULL,
    annotator          VARCHAR NOT NULL DEFAULT 'unknown',
    annotation_kind    annotation_kind NOT NULL,
    instance_label     instance_label NOT NULL DEFAULT 'semantic',
    label_native       VARCHAR,
    mask_uri           VARCHAR,
    annotation_method  VARCHAR,
    PRIMARY KEY (record_uid, label_canonical, annotator)
);


-- ---------------------------------------------------------------------
-- L4 - Cohort snapshot (frozen L1-L3 payload + catalog_sha256)
-- ---------------------------------------------------------------------
--
-- A snapshot is an immutable freeze of the matched L1-L3 rows. The
-- payload is stored as a single Parquet blob in ``l13_payload`` and
-- hashed into ``catalog_sha256`` over a deterministic canonical
-- serialisation -- so the same predicate against the same data always
-- yields the same hash, even after asynchronous writes to
-- ``l2_sensor.converted_uri`` (per STEP_BY_STEP_PLAN.md §3.4).
--
-- ``hf_publication_log`` is added in Phase 3 and remains NULL until
-- DatorCloud's ``hf_publisher`` records a successful push.
CREATE TABLE IF NOT EXISTS l4_cohort_snapshot (
    snapshot_id          VARCHAR PRIMARY KEY,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    predicate_sql        VARCHAR,
    catalog_sha256       VARCHAR NOT NULL,
    n_records            BIGINT  NOT NULL,
    schema_version       VARCHAR NOT NULL DEFAULT '1.0.0',
    l13_payload          BLOB    NOT NULL,
    hf_publication_log   VARCHAR
);


-- ---------------------------------------------------------------------
-- L4 - Evaluation set (multi-annotator GT layout per snapshot)
-- ---------------------------------------------------------------------
--
-- Per design invariant I3 (snapshot ⟂ eval-set orthogonality), multiple
-- eval sets may reference the same snapshot. Each row captures the
-- annotator columns the inter-observer pipeline reads, the target
-- labels to evaluate, and the two quantile cut-offs used to compute the
-- IO band.
CREATE TABLE IF NOT EXISTS l4_eval_set (
    eval_set_id              VARCHAR PRIMARY KEY,
    snapshot_id              VARCHAR NOT NULL REFERENCES l4_cohort_snapshot(snapshot_id),
    annotator_columns        VARCHAR[] NOT NULL,
    target_labels            VARCHAR[] NOT NULL,
    inter_observer_quantiles DOUBLE[],
    notes                    VARCHAR,
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
