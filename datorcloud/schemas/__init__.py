"""DatorCloud catalog schemas (L1-L4).

This package owns the canonical L1-L4 DDL upstreamed in Phase 1 of the DORIS
integration plan. It exposes:

* :data:`L1_L4_DDL_PATH` - on-disk path to ``l1_l4.sql``.
* :data:`SCHEMA_VERSION` - the version tag stamped into every catalog write.
* :class:`Migration` - the idempotent migration runner that applies the DDL
  to a DuckDB connection and computes a stable :attr:`schema_sha`.
"""

from __future__ import annotations

from .migrations import Migration, SCHEMA_VERSION, L1_L4_DDL_PATH

__all__ = ["Migration", "SCHEMA_VERSION", "L1_L4_DDL_PATH"]
