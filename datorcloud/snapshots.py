"""L4 cohort snapshot freeze + L4 eval-set creation.

Per STEP_BY_STEP_PLAN.md §3 step 1.4, ``snapshot_cohort()`` is the moment
where an immutable cohort identity is minted:

* The matched L1-L3 rows are deep-copied into a single Parquet blob.
* The blob is hashed (over a deterministic canonical serialisation) into
  ``catalog_sha256``.
* Both blob and hash are written into ``l4_cohort_snapshot``.

The hash is stable under later asynchronous writes to
``l2_sensor.converted_uri`` because it is computed over the frozen
payload, not against the live tables. Integration test
``doris-it-01-catalog`` assertion (c) is the system-level proof of this
behaviour.

Step 1.5 adds ``create_eval_set()`` on top: multiple eval sets may
reference the same snapshot (design invariant I3).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .schemas import SCHEMA_VERSION

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------


def _coerce_value(value):
    """Normalise a single DataFrame cell to a JSON-safe Python value."""
    if value is None:
        return None
    # Bare floats can be NaN; pd.isna also handles NaT, NA, etc, but only
    # for scalars. Lists must be checked element-wise (see below).
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return value
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, list):
        return [_coerce_value(v) for v in value]
    if hasattr(value, "tolist") and not isinstance(value, str):
        return _coerce_value(value.tolist())
    return value


def _canonical_json(df: pd.DataFrame) -> bytes:
    """Serialise *df* to deterministic JSON bytes for hashing.

    Rules:
      * Columns are sorted alphabetically.
      * Rows are sorted lexicographically using Python-level sort on the
        coerced records (pandas ``sort_values`` cannot handle columns
        that contain numpy arrays).
      * NaN / NaT become ``null``; ``pd.Timestamp`` becomes its ISO 8601
        string; ``bytes`` becomes base16; lists become JSON arrays.
    """
    if df.empty:
        return b"[]"
    sorted_cols = sorted(df.columns)
    records = [
        {k: _coerce_value(rec.get(k)) for k in sorted_cols}
        for rec in df.to_dict(orient="records")
    ]

    def _sort_key(rec):
        out = []
        for col in sorted_cols:
            v = rec[col]
            if v is None:
                # ``None`` sorts before anything else; encode as
                # (0, "") so the comparison is total.
                out.append((0, ""))
            elif isinstance(v, list):
                out.append((1, json.dumps(v, sort_keys=True, separators=(",", ":"))))
            else:
                out.append((1, _stringify_scalar(v)))
        return tuple(out)

    records.sort(key=_sort_key)
    return json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stringify_scalar(value):
    """Stringify a scalar for the canonical sort key.

    Returns a tuple of (type-rank, value) so int<float<str<bool can be
    compared without TypeErrors.
    """
    if isinstance(value, bool):
        return f"b:{int(value)}"
    if isinstance(value, (int, float)):
        return f"n:{value!r}"
    return f"s:{value!s}"


def _dataframe_to_parquet_blob(df: pd.DataFrame) -> bytes:
    """Serialise *df* to a Parquet byte blob (storage format)."""
    if df.empty:
        return b""
    table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(
        table,
        buf,
        version="2.6",
        compression="snappy",
        use_dictionary=True,
        write_statistics=False,
    )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Snapshot:
    """The frozen identity of one cohort selection."""

    snapshot_id: str
    catalog_sha256: str
    n_records: int
    predicate_sql: Optional[str]
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class EvalSet:
    """A multi-annotator GT layout applied to one snapshot."""

    eval_set_id: str
    snapshot_id: str
    annotator_columns: tuple[str, ...]
    target_labels: tuple[str, ...]
    inter_observer_quantiles: tuple[float, float] | None


def _today_iso() -> str:
    return date.today().isoformat()


def _build_snapshot_payload(
    conn: "duckdb.DuckDBPyConnection", predicate_sql: Optional[str]
) -> pd.DataFrame:
    """Run *predicate_sql* (or 'TRUE') against ``v_doris`` to get the matched rows.

    The result is the denormalised view; we then attach the L3 annotation
    rows in their original form (one row per (record_uid, label, annotator))
    so the snapshot payload captures the full multi-annotator structure
    that ``l4_eval_set`` later references.
    """
    where_clause = f"WHERE {predicate_sql}" if predicate_sql else ""
    matched_uids = conn.execute(
        f"SELECT DISTINCT record_uid FROM v_doris {where_clause}"
    ).fetchdf()
    if matched_uids.empty:
        return matched_uids.assign(layer="empty")

    # Build the layered payload: one DataFrame per layer, concatenated
    # vertically with a 'layer' discriminator column. This keeps the
    # canonical hash insensitive to layer-internal column ordering while
    # preserving every annotator / sensor row.
    uid_view = "_snapshot_uids"
    conn.register(uid_view, matched_uids)
    try:
        l1 = conn.execute(
            f"SELECT * FROM l1_experiment WHERE record_uid IN (SELECT record_uid FROM {uid_view})"
        ).fetchdf()
        l2 = conn.execute(
            f"SELECT * FROM l2_sensor WHERE record_uid IN (SELECT record_uid FROM {uid_view})"
        ).fetchdf()
        l3 = conn.execute(
            f"SELECT * FROM l3_annotation WHERE record_uid IN (SELECT record_uid FROM {uid_view})"
        ).fetchdf()
    finally:
        conn.unregister(uid_view)

    # We DROP ``l2_sensor.converted_uri`` from the canonical payload so
    # later asynchronous writes to it cannot perturb ``catalog_sha256``.
    # The snapshot stores the *cohort identity*, not the conversion
    # progress. ``converted_uri`` reappears in the live ``v_doris`` view
    # and in ``F``-operator materialisations.
    if "converted_uri" in l2.columns:
        l2 = l2.drop(columns=["converted_uri"])
    if "ingested_at" in l1.columns:
        l1 = l1.drop(columns=["ingested_at"])

    frames = []
    for name, frame in (("l1_experiment", l1), ("l2_sensor", l2), ("l3_annotation", l3)):
        if frame.empty:
            continue
        frame = frame.copy()
        frame.insert(0, "layer", name)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def snapshot_cohort(
    catalog,
    *,
    dataset_id: str,
    predicate_sql: Optional[str] = None,
    snapshot_date: Optional[str] = None,
) -> Snapshot:
    """Freeze a cohort identity into ``l4_cohort_snapshot``.

    Args:
        catalog: a :class:`ParquetCatalogComponent` (passed in to avoid an
            import cycle).
        dataset_id: logical cohort handle -- becomes the snapshot's
            ``<dataset_id>@<YYYY-MM-DD>`` prefix.
        predicate_sql: optional SQL fragment evaluated against ``v_doris``
            (e.g. ``"modality = 'CT' AND 'pelvis' = ANY(body_part)"``).
            ``None`` means "all records currently in the catalog".
        snapshot_date: ISO date string used for the snapshot id; defaults
            to today. Tests pin this to a fixed date for determinism.

    Returns:
        The :class:`Snapshot` row that was just written.
    """
    iso = snapshot_date or _today_iso()
    snapshot_id = f"{dataset_id}@{iso}"

    conn = catalog.conn
    payload = _build_snapshot_payload(conn, predicate_sql)
    n_records = (
        0
        if payload.empty or "record_uid" not in payload.columns
        else payload["record_uid"].nunique()
    )

    canonical = _canonical_json(payload)
    catalog_sha = hashlib.sha256(canonical).hexdigest()
    parquet_blob = _dataframe_to_parquet_blob(payload)

    conn.execute(
        """
        INSERT OR REPLACE INTO l4_cohort_snapshot
            (snapshot_id, created_at, predicate_sql, catalog_sha256,
             n_records, schema_version, l13_payload, hf_publication_log)
        VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, NULL)
        """,
        [snapshot_id, predicate_sql, catalog_sha, int(n_records), SCHEMA_VERSION, parquet_blob],
    )

    log.info(
        "snapshot %s frozen: n_records=%d catalog_sha256=%s",
        snapshot_id,
        n_records,
        catalog_sha,
    )
    return Snapshot(
        snapshot_id=snapshot_id,
        catalog_sha256=catalog_sha,
        n_records=int(n_records),
        predicate_sql=predicate_sql,
    )


def load_snapshot_payload(catalog, snapshot_id: str) -> pd.DataFrame:
    """Reconstruct a snapshot's frozen L1-L3 payload as a DataFrame.

    The (F) operator and Phase 3's HF publisher both call this so that
    downstream materialisation reads exactly the rows that were captured
    at snapshot time -- never the live tables.
    """
    row = catalog.conn.execute(
        "SELECT l13_payload FROM l4_cohort_snapshot WHERE snapshot_id = ?",
        [snapshot_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"snapshot not found: {snapshot_id!r}")
    blob = row[0]
    if not blob:
        return pd.DataFrame()
    table = pq.read_table(io.BytesIO(blob))
    return table.to_pandas()


def create_eval_set(
    catalog,
    *,
    eval_set_id: str,
    snapshot_id: str,
    annotator_columns: Sequence[str],
    target_labels: Sequence[str],
    inter_observer_quantiles: Sequence[float] | None = None,
    notes: Optional[str] = None,
) -> EvalSet:
    """Attach a new ``l4_eval_set`` row to *snapshot_id*.

    Per I3, the same ``snapshot_id`` may be referenced by multiple
    ``eval_set_id`` values (different annotator subsets, different
    inter-observer quantiles, etc.). The integration test asserts this.
    """
    if inter_observer_quantiles is not None:
        if len(inter_observer_quantiles) != 2:
            raise ValueError(
                "inter_observer_quantiles must have exactly two elements "
                "[low, high]; got "
                f"{list(inter_observer_quantiles)!r}"
            )

    # Validate the snapshot exists -- DuckDB's REFERENCES would also catch
    # this but a friendlier error here saves an audit trail.
    exists = catalog.conn.execute(
        "SELECT 1 FROM l4_cohort_snapshot WHERE snapshot_id = ?", [snapshot_id]
    ).fetchone()
    if exists is None:
        raise KeyError(f"snapshot not found: {snapshot_id!r}")

    catalog.conn.execute(
        """
        INSERT OR REPLACE INTO l4_eval_set
            (eval_set_id, snapshot_id, annotator_columns, target_labels,
             inter_observer_quantiles, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        [
            eval_set_id,
            snapshot_id,
            list(annotator_columns),
            list(target_labels),
            list(inter_observer_quantiles) if inter_observer_quantiles else None,
            notes,
        ],
    )

    return EvalSet(
        eval_set_id=eval_set_id,
        snapshot_id=snapshot_id,
        annotator_columns=tuple(annotator_columns),
        target_labels=tuple(target_labels),
        inter_observer_quantiles=(
            tuple(inter_observer_quantiles) if inter_observer_quantiles else None
        ),
    )


__all__ = [
    "Snapshot",
    "EvalSet",
    "snapshot_cohort",
    "create_eval_set",
    "load_snapshot_payload",
]
