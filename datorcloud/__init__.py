"""DatorCloud - A framework for managing and retrieving multimodal research data."""

from .components import (
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    MinioObjectComponent,
    ObjectRetrievalComponent,
    ParquetCatalogComponent,
    QueryComponent,
)
from .core import DatorCloudOrchestrator
from .schemas import SCHEMA_VERSION as L1_L4_SCHEMA_VERSION
from .snapshots import (
    EvalSet,
    Snapshot,
    create_eval_set,
    load_snapshot_payload,
    snapshot_cohort,
)

__version__ = "0.2.0"

__all__ = [
    "DatorCloudOrchestrator",
    "MetadataGeneratorComponent",
    "MetadataStorageComponent",
    "MinioObjectComponent",
    "ObjectRetrievalComponent",
    "ParquetCatalogComponent",
    "QueryComponent",
    "Snapshot",
    "EvalSet",
    "snapshot_cohort",
    "create_eval_set",
    "load_snapshot_payload",
    "L1_L4_SCHEMA_VERSION",
    "__version__",
]
