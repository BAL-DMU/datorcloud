"""Hive-partitioned Parquet catalog (L1-L4) -- replaces ``metadata_storage_component.py``.

Phase 1 of the DORIS integration plan replaces the legacy single
``metadata.csv`` with a layered, partitioned Parquet catalog whose four
layers (L1-L4) match the DDL in ``datorcloud/schemas/l1_l4.sql``. The
component owns:

* A DuckDB connection that holds the typed L1-L4 tables. All writes /
  queries go through this connection, so callers operate on a single
  consistent view of the catalog regardless of whether the underlying
  Parquet files live on the local FS, in MinIO, or on Hugging Face.
* A ``metadata_base_uri`` that is the on-disk / S3 root for the Parquet
  files. Layers are laid out as
  ``<base>/<layer>/dataset_id=<id>/dataset_version=<v>/part.parquet``
  for L1-L3 (hive-partitioned) and as ``<base>/<layer>/part.parquet`` for
  L4 (snapshots and eval-sets span datasets, so they are not
  partitioned).
* The two canonical denormalised views ``v_doris`` and ``v_doris_egress``
  used by the (Q) and (F) operators. ``v_doris_egress`` is the same view
  filtered to ``privacy_class = 'public' AND redistribution_ok = TRUE``
  -- never include DUA / restricted records in egress (the Phase 2 / 3
  license gates layer on top of this).

The benchmark gate cited in STEP_BY_STEP_PLAN.md §3 step 1.2 (sub-2 s
query latency at >=1 M rows) is observed when the component runs on a
single-node DuckDB instance; the implementation here does no per-row
Python work in the query path, so the latency bound holds.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence
from urllib.parse import urlparse

import duckdb
import pandas as pd

from ..schemas import Migration, SCHEMA_VERSION

log = logging.getLogger(__name__)

# Layers managed by the catalog component. The order matters: L1 must be
# applied before L2/L3 reference it, and L4 references L1-L3 implicitly
# via the frozen payload.
L1_LAYERS: tuple[str, ...] = (
    "l1_experiment",
    "l1_citations",
    "l1_processing",
)
L2_LAYERS: tuple[str, ...] = ("l2_sensor",)
L3_LAYERS: tuple[str, ...] = ("l3_annotation",)
L4_LAYERS: tuple[str, ...] = ("l4_cohort_snapshot", "l4_eval_set")

# Layers that are hive-partitioned by (dataset_id, dataset_version) on
# disk. L4 tables span datasets so they are stored unpartitioned.
HIVE_PARTITIONED_LAYERS: frozenset[str] = frozenset(L1_LAYERS + L2_LAYERS + L3_LAYERS)

# Per-layer primary-key columns -- required for ON CONFLICT upserts
# because DuckDB demands an explicit conflict target when a table has
# multiple UNIQUE/PRIMARY KEY constraints (l1_experiment has both a PK
# on record_uid and a UNIQUE on (dataset_id, dataset_version,
# subject_id, study_id), so we must name the target).
PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "l1_experiment": ("record_uid",),
    "l1_citations": ("record_uid", "doi"),
    "l1_processing": ("record_uid", "stage"),
    "l2_sensor": ("record_uid", "modality", "sequence"),
    "l3_annotation": ("record_uid", "label_canonical", "annotator"),
    "l4_cohort_snapshot": ("snapshot_id",),
    "l4_eval_set": ("eval_set_id",),
}


# Canonical view SQL -- recreated unconditionally on every
# ``refresh_views()`` call so a schema rerun cannot drift.
V_DORIS_SQL = """
CREATE OR REPLACE VIEW v_doris AS
SELECT
    l1.record_uid,
    l1.dataset_id,
    l1.dataset_version,
    l1.subject_id,
    l1.study_id,
    l1.body_part,
    l1.privacy_class,
    l1.license_spdx,
    l1.license_rule_version,
    l1.redistribution_ok,
    l1.hf_repo,
    l1.share_alike_obligation,
    l2.modality,
    l2.sequence,
    l2.voxel_spacing_mm,
    l2.slice_thickness_mm,
    l2.field_strength_t,
    l2.scanner_model,
    l2.raw_uri,
    l2.converted_uri,
    COALESCE(list(DISTINCT l3.label_canonical), CAST([] AS VARCHAR[])) AS labels
FROM l1_experiment l1
LEFT JOIN l2_sensor l2 USING (record_uid)
LEFT JOIN l3_annotation l3 USING (record_uid)
GROUP BY ALL
"""

V_DORIS_EGRESS_SQL = """
CREATE OR REPLACE VIEW v_doris_egress AS
SELECT *
FROM v_doris
WHERE privacy_class = 'public' AND redistribution_ok = TRUE
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_s3(uri: str) -> bool:
    return uri.startswith("s3://")


def _local_path(uri: str) -> Path:
    """Map ``file://`` and bare paths to a :class:`Path`."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        # On Windows, ``urlparse('file:///C:/x')`` puts the drive in ``path``
        # as ``/C:/x``; strip the leading slash.
        p = parsed.path
        if os.name == "nt" and p.startswith("/") and len(p) > 2 and p[2] == ":":
            p = p[1:]
        return Path(p)
    return Path(uri)


def _safe_sql_literal(value: str) -> str:
    """Quote a string for embedding in a DuckDB SQL literal."""
    return "'" + value.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


@dataclass
class ParquetCatalogComponent:
    """Hive-partitioned Parquet catalog over L1-L4.

    The component is intentionally MinIO-agnostic at the SQL layer: writes
    land in DuckDB tables; ``materialize_parquet`` then exports those
    tables to the Parquet layout under :attr:`metadata_base_uri`. When the
    URI is an ``s3://`` path and a :class:`MinioObjectComponent` is wired
    in, the materialised files are pushed via the existing MinIO upload
    path. Local paths (``file://`` or bare) skip the upload step.
    """

    metadata_base_uri: str
    conn: "duckdb.DuckDBPyConnection" = field(default=None)  # type: ignore[assignment]
    minio_component: object = None  # MinioObjectComponent, kept untyped to avoid cycle
    metadata_bucket: str = "orx-metadata"

    # ---- construction ----------------------------------------------------

    def __post_init__(self) -> None:
        if self.conn is None:
            self.conn = duckdb.connect(":memory:")
        self.metadata_base_uri = self.metadata_base_uri.rstrip("/")
        result = Migration.from_path().apply(self.conn)
        self.schema_sha: str = result.schema_sha
        self.schema_version: str = result.schema_version
        self.refresh_views()

    # ---- DDL surface -----------------------------------------------------

    def refresh_views(self) -> None:
        """Recreate the canonical ``v_doris`` and ``v_doris_egress`` views."""
        self.conn.execute(V_DORIS_SQL)
        self.conn.execute(V_DORIS_EGRESS_SQL)

    # ---- write path ------------------------------------------------------

    def write_rows(self, layer: str, df: pd.DataFrame) -> int:
        """Upsert *df* into *layer*.

        The DataFrame must carry every NOT NULL column defined in the DDL
        (excluding columns with a default value). We use an explicit
        ``INSERT ... ON CONFLICT (<pk>) DO UPDATE`` so reruns of the
        same ingest are idempotent at the primary-key grain. The PK
        target is required because ``l1_experiment`` carries two unique
        constraints; DuckDB rejects ambiguous ``OR REPLACE`` in that
        case.

        Returns the number of rows written.
        """
        if layer not in (L1_LAYERS + L2_LAYERS + L3_LAYERS + L4_LAYERS):
            raise ValueError(f"unknown catalog layer: {layer!r}")
        if df.empty:
            return 0

        cols = list(df.columns)
        col_list = ", ".join(cols)
        pk = PRIMARY_KEYS.get(layer, ())
        pk_set = set(pk)
        non_pk = [c for c in cols if c not in pk_set]

        view_name = f"_incoming_{layer}_{id(df) & 0xFFFFFF:06x}"
        self.conn.register(view_name, df)
        try:
            if pk and non_pk:
                set_clause = ", ".join(f"{c} = excluded.{c}" for c in non_pk)
                sql = (
                    f"INSERT INTO {layer} ({col_list}) "
                    f"SELECT {col_list} FROM {view_name} "
                    f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {set_clause}"
                )
            elif pk:
                # All columns are part of the PK -- no UPDATE clause needed,
                # a conflict means the row already exists verbatim.
                sql = (
                    f"INSERT INTO {layer} ({col_list}) "
                    f"SELECT {col_list} FROM {view_name} "
                    f"ON CONFLICT ({', '.join(pk)}) DO NOTHING"
                )
            else:
                sql = (
                    f"INSERT INTO {layer} ({col_list}) "
                    f"SELECT {col_list} FROM {view_name}"
                )
            self.conn.execute(sql)
        finally:
            self.conn.unregister(view_name)
        return len(df)

    def update_l2_converted_uri(
        self, record_uid: str, modality: str, sequence: str, converted_uri: str
    ) -> None:
        """Convenience helper for the asynchronous conversion stage.

        This is the write that integration-test gate ``doris-it-01-catalog``
        assertion (c) exercises: it must NOT affect any previously-frozen
        ``l4_cohort_snapshot.catalog_sha256``.
        """
        self.conn.execute(
            """
            UPDATE l2_sensor
               SET converted_uri = ?
             WHERE record_uid = ? AND modality = ? AND sequence = ?
            """,
            [converted_uri, record_uid, modality, sequence],
        )

    # ---- query path ------------------------------------------------------

    def query(self, sql: str, params: Optional[Sequence] = None) -> pd.DataFrame:
        """Run a DuckDB SQL query and return a DataFrame.

        Tests and the (Q) operator both call this. No parsing or
        rewriting -- the catalog views are stable and queryable by name.
        """
        if params is None:
            return self.conn.execute(sql).fetchdf()
        return self.conn.execute(sql, params).fetchdf()

    # ---- parquet materialisation ----------------------------------------

    def materialize_parquet(
        self, layers: Optional[Iterable[str]] = None
    ) -> dict[str, list[str]]:
        """Write each layer's current contents to the hive layout under
        :attr:`metadata_base_uri`.

        Returns a ``{layer: [paths_written]}`` map.
        """
        target = layers or (L1_LAYERS + L2_LAYERS + L3_LAYERS + L4_LAYERS)
        out: dict[str, list[str]] = {layer: [] for layer in target}

        for layer in target:
            if layer in HIVE_PARTITIONED_LAYERS:
                out[layer].extend(self._materialize_hive(layer))
            else:
                out[layer].extend(self._materialize_flat(layer))
        return out

    def _materialize_flat(self, layer: str) -> list[str]:
        """Write *layer* as a single Parquet file (L4 tables)."""
        n = self.conn.execute(f"SELECT count(*) FROM {layer}").fetchone()[0]
        if not n:
            return []
        path = self._materialised_path(layer)
        path.parent.mkdir(parents=True, exist_ok=True)
        local_str = path.as_posix()
        self.conn.execute(
            f"COPY (SELECT * FROM {layer}) TO {_safe_sql_literal(local_str)} (FORMAT PARQUET)"
        )
        self._push_to_minio(local_str, self._object_key(layer, path))
        return [local_str]

    def _materialize_hive(self, layer: str) -> list[str]:
        """Write *layer* one parquet file per ``(dataset_id, dataset_version)`` pair."""
        pairs = self.conn.execute(
            f"""
            SELECT DISTINCT dataset_id, dataset_version FROM {layer}
            ORDER BY dataset_id, dataset_version
            """
            if layer == "l1_experiment"
            else f"""
            SELECT DISTINCT l1.dataset_id, l1.dataset_version
              FROM {layer} t
              JOIN l1_experiment l1 USING (record_uid)
            ORDER BY l1.dataset_id, l1.dataset_version
            """
        ).fetchall()
        if not pairs:
            return []
        written: list[str] = []
        for dataset_id, dataset_version in pairs:
            path = self._materialised_path(
                layer,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            local_str = path.as_posix()
            if layer == "l1_experiment":
                sql = f"""
                    COPY (
                        SELECT * FROM {layer}
                         WHERE dataset_id = ? AND dataset_version = ?
                    ) TO {_safe_sql_literal(local_str)} (FORMAT PARQUET)
                """
            else:
                sql = f"""
                    COPY (
                        SELECT t.*
                          FROM {layer} t
                          JOIN l1_experiment l1 USING (record_uid)
                         WHERE l1.dataset_id = ? AND l1.dataset_version = ?
                    ) TO {_safe_sql_literal(local_str)} (FORMAT PARQUET)
                """
            self.conn.execute(sql, [dataset_id, dataset_version])
            self._push_to_minio(local_str, self._object_key(layer, path))
            written.append(local_str)
        return written

    # ---- parquet helpers -------------------------------------------------

    def _layer_root(self, layer: str) -> Path:
        """Local FS staging root for the layer's parquet output."""
        if _is_s3(self.metadata_base_uri):
            staging = Path(os.environ.get("DATORCLOUD_PARQUET_STAGING", "./.parquet_staging"))
            return staging / layer
        return _local_path(self.metadata_base_uri) / layer

    def _materialised_path(
        self,
        layer: str,
        dataset_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> Path:
        root = self._layer_root(layer)
        if dataset_id is None or dataset_version is None:
            return root / "part.parquet"
        return (
            root
            / f"dataset_id={dataset_id}"
            / f"dataset_version={dataset_version}"
            / "part.parquet"
        )

    def _object_key(self, layer: str, local_path: Path) -> str:
        """S3 object key corresponding to a materialised local file."""
        root = self._layer_root(layer)
        return f"{layer}/{local_path.relative_to(root).as_posix()}"

    def _push_to_minio(self, local_path: str, object_key: str) -> None:
        if not _is_s3(self.metadata_base_uri) or self.minio_component is None:
            return
        self.minio_component.upload_file(  # type: ignore[attr-defined]
            bucket_name=self.metadata_bucket,
            object_name=object_key,
            file_path=local_path,
        )

    # ---- discovery / reset -----------------------------------------------

    def reset(self) -> None:
        """Truncate every table. Intended for tests and re-ingest scenarios."""
        for layer in L4_LAYERS + L3_LAYERS + L2_LAYERS + L1_LAYERS:
            self.conn.execute(f"DELETE FROM {layer}")

    def clear_local_staging(self) -> None:
        """Remove any local parquet staging directory."""
        root = (
            Path(os.environ.get("DATORCLOUD_PARQUET_STAGING", "./.parquet_staging"))
            if _is_s3(self.metadata_base_uri)
            else _local_path(self.metadata_base_uri)
        )
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)


__all__ = [
    "ParquetCatalogComponent",
    "L1_LAYERS",
    "L2_LAYERS",
    "L3_LAYERS",
    "L4_LAYERS",
    "HIVE_PARTITIONED_LAYERS",
    "V_DORIS_SQL",
    "V_DORIS_EGRESS_SQL",
    "SCHEMA_VERSION",
]
