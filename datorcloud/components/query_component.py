"""Component that runs DuckDB SQL over MinIO-backed metadata CSVs."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

log = logging.getLogger(__name__)


class QueryComponent:
    """Component for querying metadata using DuckDB.

    The component opens an in-memory DuckDB connection, loads the ``httpfs``
    extension, and configures the S3 settings so the metadata CSV stored in
    MinIO can be queried directly via ``s3://`` paths.
    """

    DEFAULT_EXTENSION_ENV = "DUCKDB_HTTPFS_EXTENSION_PATH"
    DEFAULT_REGION = "us-east-1"
    DEFAULT_ENDPOINT = "minio:9090"

    def __init__(
        self,
        s3_region: Optional[str] = None,
        s3_endpoint: Optional[str] = None,
        s3_access_key: Optional[str] = None,
        s3_secret_key: Optional[str] = None,
        s3_use_ssl: bool = False,
        duckdb_extension_path: Optional[str] = None,
        connection: Optional["duckdb.DuckDBPyConnection"] = None,
    ) -> None:
        """Initialize the DuckDB query component.

        When ``connection`` is provided it is used as-is; the caller is
        responsible for any ``httpfs`` / S3 configuration. This path is
        typically used by tests querying local CSVs.

        Otherwise a fresh in-memory DuckDB connection is opened, ``httpfs`` is
        loaded, and the S3 settings are applied — which requires credentials.

        Args:
            s3_region: The S3 region. Defaults to ``us-east-1``.
            s3_endpoint: MinIO server endpoint. Defaults to ``minio:9090``.
            s3_access_key: MinIO access key. **Required** when ``connection`` is None.
            s3_secret_key: MinIO secret key. **Required** when ``connection`` is None.
            s3_use_ssl: Whether to use SSL for S3 connections.
            duckdb_extension_path: Optional explicit path to ``httpfs.duckdb_extension``.
                Falls back to the ``DUCKDB_HTTPFS_EXTENSION_PATH`` env var, then to
                DuckDB's default extension resolution.
            connection: Optional pre-built DuckDB connection. Mainly for tests.

        Raises:
            ValueError: When ``connection`` is None and credentials are missing.
        """
        if connection is not None:
            self.conn = connection
            return

        self.conn = duckdb.connect(":memory:")
        self._configure_httpfs(duckdb_extension_path)

        if not s3_access_key or not s3_secret_key:
            raise ValueError(
                "S3 credentials are required when QueryComponent builds its "
                "own DuckDB connection. Pass `s3_access_key`/`s3_secret_key` "
                "or inject a pre-configured `connection` (tests typically do "
                "the latter). Production callers should configure S3_ACCESS_KEY "
                "and S3_SECRET_KEY in their .env."
            )

        self._configure_s3(
            s3_region or self.DEFAULT_REGION,
            s3_endpoint or self.DEFAULT_ENDPOINT,
            s3_access_key,
            s3_secret_key,
            s3_use_ssl,
        )

    def _configure_httpfs(self, explicit_path: Optional[str]) -> None:
        """Load the httpfs extension, trying several strategies in order:

        1. Plain ``LOAD httpfs`` — works when a healthy copy is already cached.
        2. ``LOAD '<path>'`` from an explicit path or ``DUCKDB_HTTPFS_EXTENSION_PATH``.
        3. ``INSTALL httpfs`` from the DuckDB extension repository.
        4. ``FORCE INSTALL httpfs`` to overwrite a stale or corrupt local cache.
           This rescues containers where a prebaked ``httpfs.duckdb_extension.info``
           file was written in a format the current DuckDB cannot deserialize
           (the classic ``field id mismatch, expected: 100, got: NNNN`` error).
        """
        try:
            self.conn.execute("LOAD httpfs")
            log.debug("Loaded DuckDB httpfs extension via standard resolution")
            return
        except Exception as exc:
            log.debug("Standard httpfs load failed: %s", exc)

        candidate = explicit_path or os.environ.get(self.DEFAULT_EXTENSION_ENV)
        if candidate:
            try:
                self.conn.execute(f"LOAD '{candidate}'")
                log.info("Loaded DuckDB httpfs extension from %s", candidate)
                return
            except Exception as exc:
                log.warning("Failed to load httpfs from %s: %s", candidate, exc)

        last_exc: Optional[Exception] = None
        for stmt in ("INSTALL httpfs", "FORCE INSTALL httpfs"):
            try:
                self.conn.execute(stmt)
                self.conn.execute("LOAD httpfs")
                log.info("Installed and loaded DuckDB httpfs extension via `%s`", stmt)
                return
            except Exception as exc:
                log.warning("`%s` failed: %s", stmt, exc)
                last_exc = exc

        log.error("Could not load DuckDB httpfs extension: %s", last_exc)
        raise RuntimeError("Failed to load httpfs extension") from last_exc

    def _configure_s3(
        self,
        s3_region: str,
        s3_endpoint: str,
        s3_access_key: str,
        s3_secret_key: str,
        s3_use_ssl: bool,
    ) -> None:
        """Configure DuckDB S3 settings."""
        self.conn.execute(f"SET s3_region='{s3_region}'")
        self.conn.execute(f"SET s3_access_key_id='{s3_access_key}'")
        self.conn.execute(f"SET s3_secret_access_key='{s3_secret_key}'")
        self.conn.execute(f"SET s3_endpoint='{s3_endpoint}'")
        self.conn.execute("SET s3_url_style='path'")
        self.conn.execute(f"SET s3_use_ssl={str(s3_use_ssl).lower()}")

    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a DuckDB query and return the results as a DataFrame."""
        try:
            return self.conn.execute(query).fetchdf()
        except Exception:
            log.exception("Error executing query: %s", query)
            raise

    @staticmethod
    def _build_where_clause(filters: Dict[str, Any]) -> str:
        """Translate a ``{column: value}`` filter dict into a SQL WHERE clause.

        Strings are quoted; lists become ``IN (...)``; everything else is rendered
        with ``str()``. Returns an empty string when ``filters`` is falsy.
        """
        if not filters:
            return ""

        clauses: List[str] = []
        for column, value in filters.items():
            if isinstance(value, str):
                escaped = value.replace("'", "''")
                clauses.append(f"{column} = '{escaped}'")
            elif isinstance(value, (list, tuple, set)):
                rendered = []
                for v in value:
                    if isinstance(v, str):
                        rendered.append("'" + v.replace("'", "''") + "'")
                    else:
                        rendered.append(str(v))
                if rendered:
                    clauses.append(f"{column} IN ({', '.join(rendered)})")
            elif value is None:
                clauses.append(f"{column} IS NULL")
            else:
                clauses.append(f"{column} = {value}")

        return " WHERE " + " AND ".join(clauses) if clauses else ""

    def query_metadata(
        self,
        metadata_file: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Query the metadata CSV file with optional filters."""
        query = f"SELECT * FROM read_csv_auto('{metadata_file}')"
        query += self._build_where_clause(filters or {})
        if limit:
            query += f" LIMIT {int(limit)}"
        return self.execute_query(query)

    def get_object_paths(
        self,
        metadata_file: str,
        dataset: str,
        data_bucket: str = "orx-datalake",
        **filters: Any,
    ) -> List[Dict[str, str]]:
        """Get S3 object paths for files matching the given criteria."""
        filter_dict: Dict[str, Any] = {"dataset": dataset}
        filter_dict.update(filters)
        where_clause = self._build_where_clause(filter_dict)
        query = f"""
            SELECT
                experiment,
                's3://{data_bucket}/' || file_path AS full_path,
                file_path AS object_name,
                subfolder,
                file_name
            FROM read_csv_auto('{metadata_file}')
            {where_clause}
        """
        return self.execute_query(query).to_dict("records")
