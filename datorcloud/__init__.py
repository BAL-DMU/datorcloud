"""DatorCloud - A framework for managing and retrieving multimodal research data."""

from .components import (
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    MinioObjectComponent,
    ObjectRetrievalComponent,
    QueryComponent,
)
from .core import DatorCloudOrchestrator

__version__ = "0.1.0"

__all__ = [
    "DatorCloudOrchestrator",
    "MetadataGeneratorComponent",
    "MetadataStorageComponent",
    "MinioObjectComponent",
    "ObjectRetrievalComponent",
    "QueryComponent",
    "__version__",
]
