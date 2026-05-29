"""Dagster sensor: re-enqueue evaluation when model weights change (Phase 5)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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


MODELS_PREFIX = os.environ.get("DORIS_MODELS_PREFIX", "s3://doris-models/")
STATE_DIR = Path(os.environ.get("DORIS_SENSOR_STATE", "/tmp/doris_sensor_state"))


def _family_weights_digest(family: str, root: Path) -> str:
    """Hash all files under ``<root>/<family>/`` for change detection."""
    family_root = root / family
    if not family_root.is_dir():
        return ""
    h = hashlib.sha256()
    for path in sorted(family_root.rglob("*")):
        if path.is_file():
            h.update(path.name.encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def weights_changed(family: str, models_root: Path, state_dir: Path = STATE_DIR) -> bool:
    """Return True when *family* weights digest differs from last seen."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / f"{family}.json"
    current = _family_weights_digest(family, models_root)
    if not current:
        return False
    previous = ""
    if state_file.exists():
        previous = json.loads(state_file.read_text(encoding="utf-8")).get("digest", "")
    if current == previous:
        return False
    state_file.write_text(json.dumps({"digest": current}), encoding="utf-8")
    return True


def build_eval_run_requests(
    *,
    families: Sequence[str],
    eval_set_ids: Sequence[str],
    snapshot_id: str,
    models_root: Path,
    source: str = "hf",
    hub_id: str = "jaghbal/msk-imaging",
) -> List[Dict[str, Any]]:
    """Build run configs for families whose weights changed."""
    requests: List[Dict[str, Any]] = []
    for family in families:
        if not weights_changed(family, models_root):
            continue
        for eval_set_id in eval_set_ids:
            requests.append({
                "run_key": f"{family}:{eval_set_id}:{snapshot_id}",
                "tags": {
                    "doris/family": family,
                    "doris/eval_set_id": eval_set_id,
                    "doris/snapshot_id": snapshot_id,
                },
                "run_config": {
                    "snapshot_id": snapshot_id,
                    "eval_set_id": eval_set_id,
                    "families": [family],
                    "source": source,
                    "hub_id": hub_id,
                    "deterministic": True,
                },
            })
    return requests


if sensor is not None:

    @sensor(
        name="doris_model_weights_sensor",
        minimum_interval_seconds=300,
        default_status=DefaultSensorStatus.STOPPED,
        description=(
            "Enqueue run_evaluation when weights under "
            "s3://doris-models/<family>/ change."
        ),
    )
    def doris_model_weights_sensor(context: SensorEvaluationContext):
        models_root = Path(os.environ.get("DORIS_MODELS_LOCAL", "/models"))
        families = os.environ.get(
            "DORIS_FAMILIES", "unet_totalsegmentator,sam_medsam2"
        ).split(",")
        eval_sets = os.environ.get(
            "DORIS_EVAL_SETS", "shoulder_ct_v3"
        ).split(",")
        snapshot_id = os.environ.get(
            "DORIS_SNAPSHOT_ID", "totalsegmentator@2026-05-28"
        )

        for req in build_eval_run_requests(
            families=[f.strip() for f in families if f.strip()],
            eval_set_ids=[e.strip() for e in eval_sets if e.strip()],
            snapshot_id=snapshot_id,
            models_root=models_root,
        ):
            context.log.info("Enqueue evaluation: %s", req["run_key"])
            yield RunRequest(
                run_key=req["run_key"],
                tags=req["tags"],
                run_config=req["run_config"],
            )

else:
    doris_model_weights_sensor = None  # type: ignore[misc, assignment]

__all__ = [
    "build_eval_run_requests",
    "weights_changed",
    "doris_model_weights_sensor",
]
