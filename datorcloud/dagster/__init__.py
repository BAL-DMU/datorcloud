"""Dagster integration for DatorCloud.

The ``dagster`` PyPI package is an optional runtime dependency: it is
required to actually execute the asset pipeline, but read-only helpers
such as :func:`evaluation_sensor.build_eval_run_requests` (Phase 5
weights-change detection) are pure-Python and must remain importable
in environments that ship without ``dagster`` (CI test runners, the
``msk-ai-trust-to-deploy`` codespace, ...). So we load the
asset-bearing submodule lazily and tolerate its absence.
"""

import logging as _logging

_log = _logging.getLogger(__name__)

try:
    from .component_assets import (
        DatorCloudComponents,
        DatorCloudResource,
        GenerateMetadataConfig,
        QueryMetadataConfig,
        RetrieveObjectsConfig,
        UploadDatasetsConfig,
        component_assets,
        generate_metadata,
        query_metadata,
        retrieve_objects,
        upload_datasets,
    )
except ImportError as exc:  # pragma: no cover - environment dependent
    _log.warning(
        "datorcloud.dagster: asset pipeline unavailable -- %s", exc
    )
    DatorCloudComponents = None  # type: ignore[assignment]
    DatorCloudResource = None  # type: ignore[assignment]
    GenerateMetadataConfig = None  # type: ignore[assignment]
    QueryMetadataConfig = None  # type: ignore[assignment]
    RetrieveObjectsConfig = None  # type: ignore[assignment]
    UploadDatasetsConfig = None  # type: ignore[assignment]
    component_assets = None  # type: ignore[assignment]
    generate_metadata = None  # type: ignore[assignment]
    query_metadata = None  # type: ignore[assignment]
    retrieve_objects = None  # type: ignore[assignment]
    upload_datasets = None  # type: ignore[assignment]

from .catalog_publish_sensor import (
    CatalogDigest,
    DEFAULT_HUB_ALIASES,
    LAYER_NAMES,
    build_republish_run_requests,
    changed_layers,
    digest_catalog,
    doris_catalog_publish_sensor,
)
from .evaluation_sensor import (
    build_eval_run_requests,
    doris_model_weights_sensor,
    weights_changed,
)

__all__ = [
    "DatorCloudComponents",
    "DatorCloudResource",
    "GenerateMetadataConfig",
    "QueryMetadataConfig",
    "RetrieveObjectsConfig",
    "UploadDatasetsConfig",
    "component_assets",
    "generate_metadata",
    "query_metadata",
    "retrieve_objects",
    "upload_datasets",
    "build_eval_run_requests",
    "doris_model_weights_sensor",
    "weights_changed",
    "CatalogDigest",
    "DEFAULT_HUB_ALIASES",
    "LAYER_NAMES",
    "build_republish_run_requests",
    "changed_layers",
    "digest_catalog",
    "doris_catalog_publish_sensor",
]
