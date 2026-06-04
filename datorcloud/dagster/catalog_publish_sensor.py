"""Dagster sensor: republish HF catalog sidecars when L1-L4 mutates.

Cross-cutting workstream "Dagster sensors" in
``msk-ai-trust-to-deploy/99_integration_plan/STEP_BY_STEP_PLAN.md §8``
declares two sensors:

1. **Model-weights sensor** (already implemented in
   :mod:`datorcloud.dagster.evaluation_sensor`).
2. **HF catalog republish sensor** -- "re-pushes the catalog Parquet
   sidecars whenever L1-L4 mutates". This is that sensor.

The sensor watches the L1-L4 Parquet roots managed by
:class:`ParquetCatalogComponent` (local file URIs are supported
directly; S3 / MinIO roots can be polled via the same content-digest
trick once an ``fsspec`` mapping is set, but the v1 implementation
focuses on the local-tree path used by integration tests and offline
runs). Whenever the SHA-256 of the *concatenated* file listing
changes -- i.e. any L1-L4 Parquet write -- a republish ``RunRequest``
is yielded with the affected layers and the candidate hub policy
aliases inherited from
:mod:`datorcloud_client.hf_publish` (``HUB_CC_BY_UMBRELLA``,
``HUB_CC_BY_SA``, ``HUB_VISCERAL_META``).

This module is a thin orchestration layer; the actual republishing
runs through ``HFPublisherComponent.publish_to_hub(snapshot_id,
hub_id, ..., metadata_only=True)`` so blobs are never re-uploaded
unnecessarily.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from dagster import (
        DefaultSensorStatus,
        RunRequest,
        SensorEvaluationContext,
        sensor,
    )
except ImportError:  # pragma: no cover - optional dependency
    DefaultSensorStatus = None
    RunRequest = None
    SensorEvaluationContext = None
    sensor = None


LAYER_NAMES = (
    "l1_experiment",
    "l1_citations",
    "l1_processing",
    "l2_sensor",
    "l3_annotation",
    "l4_cohort_snapshot",
    "l4_eval_set",
)

# Aliases that resolve via datorcloud_client.hf_publish.resolve_hub_policy.
# Listed here so the sensor stays self-contained.
DEFAULT_HUB_ALIASES = ("cc_by_umbrella", "cc_by_sa_isolated", "visceral_meta")

STATE_DIR = Path(os.environ.get("DORIS_SENSOR_STATE", "/tmp/doris_sensor_state"))


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogDigest:
    """Per-layer SHA-256 of the Parquet files under a catalog root."""

    layer_digests: Dict[str, str] = field(default_factory=dict)
    layer_files: Dict[str, List[str]] = field(default_factory=dict)
    root: str = ""

    @property
    def combined(self) -> str:
        h = hashlib.sha256()
        for layer in sorted(self.layer_digests):
            h.update(f"{layer}\t{self.layer_digests[layer]}\n".encode("utf-8"))
        return h.hexdigest()


def _layer_files(root: Path, layer: str) -> List[Path]:
    layer_root = root / layer
    if not layer_root.is_dir():
        return []
    return sorted(p for p in layer_root.rglob("*.parquet") if p.is_file())


def digest_catalog(root: Path | str, *, layers: Sequence[str] = LAYER_NAMES) -> CatalogDigest:
    """Return per-layer Parquet digests under *root* (local FS only)."""
    root_path = Path(root)
    layer_digests: Dict[str, str] = {}
    layer_files: Dict[str, List[str]] = {}
    for layer in layers:
        files = _layer_files(root_path, layer)
        h = hashlib.sha256()
        names: List[str] = []
        for f in files:
            rel = f.relative_to(root_path).as_posix()
            file_sha = hashlib.sha256(f.read_bytes()).hexdigest()
            h.update(f"{rel}\t{file_sha}\n".encode("utf-8"))
            names.append(rel)
        layer_digests[layer] = h.hexdigest()
        layer_files[layer] = names
    return CatalogDigest(
        layer_digests=layer_digests,
        layer_files=layer_files,
        root=str(root_path),
    )


def changed_layers(
    previous: Optional[CatalogDigest], current: CatalogDigest
) -> List[str]:
    """Return layers whose digest moved between *previous* and *current*."""
    if previous is None:
        return [layer for layer, digest in current.layer_digests.items() if digest]
    out: List[str] = []
    for layer, digest in current.layer_digests.items():
        if previous.layer_digests.get(layer) != digest:
            out.append(layer)
    return out


def _state_file(state_dir: Path = STATE_DIR) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "catalog_digest.json"


def _load_state(state_dir: Path = STATE_DIR) -> Optional[CatalogDigest]:
    f = _state_file(state_dir)
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    return CatalogDigest(
        layer_digests=dict(data.get("layer_digests", {})),
        layer_files={k: list(v) for k, v in data.get("layer_files", {}).items()},
        root=str(data.get("root", "")),
    )


def _save_state(digest: CatalogDigest, state_dir: Path = STATE_DIR) -> None:
    _state_file(state_dir).write_text(
        json.dumps(
            {
                "layer_digests": digest.layer_digests,
                "layer_files": digest.layer_files,
                "root": digest.root,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public sensor body (also usable from unit tests directly)
# ---------------------------------------------------------------------------


def build_republish_run_requests(
    *,
    catalog_root: Path | str,
    hub_aliases: Sequence[str] = DEFAULT_HUB_ALIASES,
    snapshot_id: Optional[str] = None,
    state_dir: Path = STATE_DIR,
) -> List[Dict[str, Any]]:
    """Return run configs for every hub alias when L1-L4 has mutated.

    Args:
        catalog_root: Local FS root holding ``l1_experiment/``,
            ``l2_sensor/``, ... Parquet directories.
        hub_aliases: Hub policies whose catalog sidecars must be
            refreshed when *any* L1-L4 layer mutates.
        snapshot_id: Optional latest snapshot id to pass through. When
            unset, the sensor only refreshes the per-layer sidecars
            (``catalog/{l1,l2,l3,l4_*}.parquet``).
        state_dir: On-disk cache that stores the last seen digest.

    Returns:
        A list of run config dicts -- one per hub alias whose
        sidecars need refreshing. The list is empty when no layer
        mutated since the last poll.
    """
    current = digest_catalog(catalog_root)
    previous = _load_state(state_dir)
    layers = changed_layers(previous, current)
    if not layers:
        return []

    requests: List[Dict[str, Any]] = []
    for alias in hub_aliases:
        requests.append({
            "run_key": f"catalog_republish:{alias}:{current.combined}",
            "tags": {
                "doris/sensor": "catalog_publish",
                "doris/hub_alias": alias,
                "doris/changed_layers": ",".join(layers),
            },
            "run_config": {
                "hub_alias": alias,
                "snapshot_id": snapshot_id,
                "changed_layers": list(layers),
                "catalog_root": str(catalog_root),
                "catalog_combined_sha": current.combined,
                "metadata_only": True,
            },
        })
    _save_state(current, state_dir)
    return requests


if sensor is not None:

    @sensor(
        name="doris_catalog_publish_sensor",
        minimum_interval_seconds=600,
        default_status=DefaultSensorStatus.STOPPED,
        description=(
            "Republish HF catalog sidecars when L1-L4 mutates "
            "(STEP_BY_STEP_PLAN.md §8 row 4)."
        ),
    )
    def doris_catalog_publish_sensor(context: SensorEvaluationContext):
        catalog_root = os.environ.get(
            "DORIS_CATALOG_ROOT", "/var/datorcloud/catalog"
        )
        hub_aliases = tuple(
            a.strip()
            for a in os.environ.get(
                "DORIS_HUB_ALIASES", ",".join(DEFAULT_HUB_ALIASES)
            ).split(",")
            if a.strip()
        )
        snapshot_id = os.environ.get("DORIS_SNAPSHOT_ID")

        for req in build_republish_run_requests(
            catalog_root=catalog_root,
            hub_aliases=hub_aliases,
            snapshot_id=snapshot_id,
        ):
            context.log.info(
                "doris.catalog_publish_sensor: %s (layers=%s)",
                req["run_key"], req["tags"]["doris/changed_layers"],
            )
            yield RunRequest(
                run_key=req["run_key"],
                tags=req["tags"],
                run_config=req["run_config"],
            )

else:
    doris_catalog_publish_sensor = None  # type: ignore[misc, assignment]


__all__ = [
    "CatalogDigest",
    "LAYER_NAMES",
    "DEFAULT_HUB_ALIASES",
    "build_republish_run_requests",
    "changed_layers",
    "digest_catalog",
    "doris_catalog_publish_sensor",
]
