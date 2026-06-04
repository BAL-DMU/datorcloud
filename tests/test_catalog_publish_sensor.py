"""Unit tests for the HF catalog republish sensor.

Cross-cutting workstream "Dagster sensors" -- the second sensor in
``msk-ai-trust-to-deploy/99_integration_plan/STEP_BY_STEP_PLAN.md §8``
re-pushes ``catalog/<layer>.parquet`` sidecars whenever any L1-L4
layer mutates.

These tests pin the sensor's pure-Python core
(:func:`build_republish_run_requests`,
:func:`digest_catalog`, :func:`changed_layers`); the Dagster-decorated
``doris_catalog_publish_sensor`` is imported in the asset tests only
when ``dagster`` is installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from datorcloud.dagster.catalog_publish_sensor import (
    DEFAULT_HUB_ALIASES,
    LAYER_NAMES,
    build_republish_run_requests,
    changed_layers,
    digest_catalog,
)


def _write_parquet(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


@pytest.fixture()
def catalog_root(tmp_path):
    """Lay out a minimal L1-L4 catalog with one parquet file per layer."""
    root = tmp_path / "catalog"
    for layer in LAYER_NAMES:
        _write_parquet(root / layer / "part.parquet", f"seed:{layer}".encode())
    return root


def test_digest_catalog_lists_every_layer(catalog_root):
    digest = digest_catalog(catalog_root)
    for layer in LAYER_NAMES:
        assert layer in digest.layer_digests
        assert digest.layer_digests[layer], layer
        assert digest.layer_files[layer] == [f"{layer}/part.parquet"]


def test_digest_catalog_is_deterministic(catalog_root):
    a = digest_catalog(catalog_root)
    b = digest_catalog(catalog_root)
    assert a.layer_digests == b.layer_digests
    assert a.combined == b.combined


def test_changed_layers_against_empty_state(catalog_root):
    current = digest_catalog(catalog_root)
    out = changed_layers(None, current)
    assert sorted(out) == sorted(LAYER_NAMES)


def test_changed_layers_after_mutation(catalog_root):
    a = digest_catalog(catalog_root)
    (catalog_root / "l1_experiment" / "part.parquet").write_bytes(b"v2")
    b = digest_catalog(catalog_root)
    assert changed_layers(a, b) == ["l1_experiment"]


def test_no_request_on_clean_state(catalog_root, tmp_path, monkeypatch):
    monkeypatch.setenv("DORIS_SENSOR_STATE", str(tmp_path / "state"))
    from datorcloud.dagster import catalog_publish_sensor as mod

    state_dir = tmp_path / "state"
    first = build_republish_run_requests(
        catalog_root=catalog_root,
        state_dir=state_dir,
    )
    assert len(first) == len(DEFAULT_HUB_ALIASES)
    again = build_republish_run_requests(
        catalog_root=catalog_root,
        state_dir=state_dir,
    )
    assert again == []


def test_mutation_yields_one_request_per_alias(catalog_root, tmp_path):
    state_dir = tmp_path / "state"
    build_republish_run_requests(catalog_root=catalog_root, state_dir=state_dir)

    (catalog_root / "l4_cohort_snapshot" / "part.parquet").write_bytes(b"v2")
    out = build_republish_run_requests(
        catalog_root=catalog_root,
        state_dir=state_dir,
    )
    aliases = sorted({r["tags"]["doris/hub_alias"] for r in out})
    assert aliases == sorted(DEFAULT_HUB_ALIASES)
    for req in out:
        assert "l4_cohort_snapshot" in req["tags"]["doris/changed_layers"].split(",")
        assert req["run_config"]["metadata_only"] is True
        assert req["run_config"]["catalog_root"] == str(catalog_root)


def test_run_key_includes_combined_sha(catalog_root, tmp_path):
    state_dir = tmp_path / "state"
    out = build_republish_run_requests(
        catalog_root=catalog_root, state_dir=state_dir
    )
    for req in out:
        # ``catalog_republish:<alias>:<sha>``
        parts = req["run_key"].split(":")
        assert parts[0] == "catalog_republish"
        assert parts[1] in DEFAULT_HUB_ALIASES
        assert len(parts[2]) == 64
