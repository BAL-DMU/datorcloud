"""Idempotent DDL migration runner for the DORIS L1-L4 catalog.

The migration runner reads ``l1_l4.sql`` and applies it to a DuckDB
connection. Every statement in the DDL is guarded with ``IF NOT EXISTS``
so re-running the migration is a no-op. The runner also exposes
:attr:`schema_sha`, a SHA-256 digest of the *canonical* DDL source --
two runs against the same checkout produce identical hashes, which is
the gate ``doris-it-01-catalog`` assertion (a) checks.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import duckdb

log = logging.getLogger(__name__)

# Schema version tag stamped into every catalog snapshot. Bump this when
# the DDL changes in a way that requires re-running ``apply()``.
SCHEMA_VERSION = "1.0.0"

# On-disk path to the canonical DDL.
L1_L4_DDL_PATH: Path = Path(__file__).resolve().parent / "l1_l4.sql"


# ---------------------------------------------------------------------------
# SQL splitting
# ---------------------------------------------------------------------------


def _strip_comments(text: str) -> str:
    """Remove ``--`` line comments while preserving line numbers."""
    out_lines = []
    for line in text.splitlines():
        # We do NOT strip comments inside string literals; the DDL does not
        # use literal ``--`` inside any string.
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script into statements on bare ``;`` separators.

    DuckDB accepts multiple statements per ``execute`` call only via the
    streaming API in newer releases; for portability we split and submit
    one at a time. The splitter ignores semicolons inside single-quoted
    strings; our DDL has none today but we guard against future changes.
    """
    sql = _strip_comments(sql)
    statements: list[str] = []
    buf: list[str] = []
    in_string = False
    for ch in sql:
        if ch == "'":
            in_string = not in_string
            buf.append(ch)
        elif ch == ";" and not in_string:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _canonical_ddl_text(raw: str) -> str:
    """Normalise the DDL text so the schema hash ignores cosmetic edits.

    Strips comments, collapses whitespace inside each statement, and
    re-joins on a single ``;\\n``. Two checkouts whose DDL differs only
    in comments / whitespace produce identical ``schema_sha`` values.
    """
    stmts = _split_statements(raw)
    return ";\n".join(re.sub(r"\s+", " ", s).strip() for s in stmts) + ";\n"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Migration:
    """Apply ``l1_l4.sql`` to a DuckDB connection.

    Usage
    -----
    >>> import duckdb
    >>> from datorcloud.schemas import Migration
    >>> conn = duckdb.connect(":memory:")
    >>> m = Migration.from_path()
    >>> m.apply(conn)
    >>> m.apply(conn)            # idempotent: no error on a second call
    >>> m.schema_sha             # doctest: +ELLIPSIS
    '...'
    """

    ddl_text: str
    schema_sha: str
    schema_version: str = SCHEMA_VERSION

    # ---- constructors -----------------------------------------------------

    @classmethod
    def from_path(cls, path: Optional[Path] = None) -> "Migration":
        path = Path(path) if path is not None else L1_L4_DDL_PATH
        text = path.read_text(encoding="utf-8")
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str) -> "Migration":
        canonical = _canonical_ddl_text(text)
        sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(ddl_text=text, schema_sha=sha)

    # ---- application ------------------------------------------------------

    def statements(self) -> list[str]:
        return _split_statements(self.ddl_text)

    def apply(self, conn: "duckdb.DuckDBPyConnection") -> "MigrationResult":
        """Apply the DDL to *conn*. Returns a result with stage counts."""
        n_applied = 0
        n_skipped = 0
        for stmt in self.statements():
            try:
                conn.execute(stmt)
                n_applied += 1
            except duckdb.CatalogException as exc:
                # Defensive: DuckDB ``CREATE TYPE IF NOT EXISTS`` works since
                # 1.2 but older builds in the wild fall through to here. The
                # net effect is identical -- type already exists.
                msg = str(exc)
                if "already exists" in msg:
                    log.debug("skipping already-applied statement: %s", msg)
                    n_skipped += 1
                else:
                    raise
        return MigrationResult(
            schema_sha=self.schema_sha,
            schema_version=self.schema_version,
            n_applied=n_applied,
            n_skipped=n_skipped,
        )


@dataclass(frozen=True)
class MigrationResult:
    """Summary of one :meth:`Migration.apply` invocation."""

    schema_sha: str
    schema_version: str
    n_applied: int
    n_skipped: int


__all__ = [
    "Migration",
    "MigrationResult",
    "SCHEMA_VERSION",
    "L1_L4_DDL_PATH",
]
