"""Phase 1 step 1.1 gate: DDL migration is idempotent.

Per STEP_BY_STEP_PLAN.md §3 step 1.1, ``schemas/l1_l4.sql`` must:

  (a) apply cleanly to a fresh DuckDB connection,
  (b) re-apply without error (idempotent),
  (c) expose a stable ``schema_sha`` across two runs on an unchanged
      checkout (this is the same property that integration-test
      ``doris-it-01-catalog`` assertion (a) checks system-wide).
"""

from __future__ import annotations

import duckdb
import pytest

from datorcloud.schemas import Migration, SCHEMA_VERSION


def test_schema_version_string_present() -> None:
    assert SCHEMA_VERSION.count(".") == 2


def test_apply_creates_every_layer() -> None:
    conn = duckdb.connect(":memory:")
    Migration.from_path().apply(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
        ).fetchall()
    }
    expected = {
        "l1_experiment",
        "l1_citations",
        "l1_processing",
        "l2_sensor",
        "l3_annotation",
        "l4_cohort_snapshot",
        "l4_eval_set",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_apply_creates_every_enum() -> None:
    conn = duckdb.connect(":memory:")
    Migration.from_path().apply(conn)
    type_names = {
        row[0] for row in conn.execute("SELECT type_name FROM duckdb_types()").fetchall()
    }
    for enum in ("privacy_class", "annotation_kind", "instance_label", "processing_stage"):
        assert enum in type_names, f"ENUM {enum!r} not registered"


def test_apply_is_idempotent_no_errors() -> None:
    conn = duckdb.connect(":memory:")
    m = Migration.from_path()
    r1 = m.apply(conn)
    r2 = m.apply(conn)
    # All statements either applied or were silently skipped because
    # the entity already exists; either way no error escapes.
    assert r1.schema_sha == r2.schema_sha
    assert r1.schema_version == r2.schema_version


def test_schema_sha_stable_across_reruns(tmp_path) -> None:
    """``schema_sha`` is a pure function of the DDL text, not of the
    connection state. Two runs on the same checkout produce identical
    hashes.
    """
    a = Migration.from_path().schema_sha
    b = Migration.from_path().schema_sha
    assert a == b
    assert len(a) == 64  # hex sha-256


def test_schema_sha_insensitive_to_comments() -> None:
    """Comments and surrounding whitespace must not affect ``schema_sha``.

    Token-level whitespace inside a statement (e.g. ``(x INTEGER)`` vs
    ``( x INTEGER )``) IS semantically distinct in the DDL and therefore
    DOES change the hash -- that distinction is intentional.
    """
    base = """
    -- one comment
    CREATE TABLE IF NOT EXISTS demo (x INTEGER);
    """
    same_no_comments = "\n   CREATE TABLE IF NOT EXISTS demo (x INTEGER);\n"
    different_comment = """
    -- a completely different comment
    CREATE TABLE IF NOT EXISTS demo (x INTEGER);
    """
    assert (
        Migration.from_text(base).schema_sha
        == Migration.from_text(same_no_comments).schema_sha
        == Migration.from_text(different_comment).schema_sha
    )


def test_l1_unique_key_includes_study_id() -> None:
    """STEP_BY_STEP_PLAN.md §3 step 1.1: DICOM rows with multiple
    ``study_id`` values for the same ``subject_id`` must not collide.
    """
    conn = duckdb.connect(":memory:")
    Migration.from_path().apply(conn)
    conn.execute(
        """
        INSERT INTO l1_experiment
            (record_uid, dataset_id, dataset_version, subject_id, study_id,
             privacy_class, license_spdx, redistribution_ok)
        VALUES
            ('u1', 'tcia', 'idc_v18', 'sub-001', 'study-A',
             'public', 'CC-BY-4.0', TRUE),
            ('u2', 'tcia', 'idc_v18', 'sub-001', 'study-B',
             'public', 'CC-BY-4.0', TRUE)
        """
    )
    n = conn.execute("SELECT count(*) FROM l1_experiment").fetchone()[0]
    assert n == 2


def test_l2_unique_key_splits_compound_modalities() -> None:
    """L2 must accept the same record under multiple (modality, sequence)
    pairs so CVPR ``"MR (T2, ADC)"`` strings split losslessly.
    """
    conn = duckdb.connect(":memory:")
    Migration.from_path().apply(conn)
    conn.execute(
        """
        INSERT INTO l1_experiment
            (record_uid, dataset_id, dataset_version, subject_id, study_id,
             privacy_class, license_spdx, redistribution_ok)
        VALUES ('u1', 'mri_ts', 'v2', 'sub-001', '',
                'public', 'CC-BY-4.0', TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO l2_sensor
            (record_uid, modality, sequence, raw_format)
        VALUES
            ('u1', 'MR', 'T2', 'nii.gz'),
            ('u1', 'MR', 'ADC', 'nii.gz')
        """
    )
    n = conn.execute("SELECT count(*) FROM l2_sensor").fetchone()[0]
    assert n == 2
