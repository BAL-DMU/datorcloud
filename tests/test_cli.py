"""Smoke tests for the ``datorcloud`` CLI."""

from __future__ import annotations

import json

import pytest

from datorcloud import __version__
from datorcloud import cli


def test_cli_version(capsys):
    rc = cli.main(["version"])
    captured = capsys.readouterr()
    assert rc == 0
    assert __version__ in captured.out


def test_cli_invalid_command(capsys):
    with pytest.raises(SystemExit):
        cli.main(["does-not-exist"])


def test_parse_kv_pairs_rejects_bad_input():
    with pytest.raises(Exception):
        cli._parse_kv_pairs(["bad-format"])


def test_parse_kv_pairs_basic():
    assert cli._parse_kv_pairs(["a=b", "c=d"]) == {"a": "b", "c": "d"}


def test_parse_filters_basic():
    assert cli._parse_filters(["camera_id=camera01"]) == {"camera_id": "camera01"}


def test_cli_query_sql_against_local_catalog(tmp_path, capsys, monkeypatch):
    """Phase 1 §3 step 1.3 CLI gate.

    ``python -m datorcloud query --sql "SELECT count(*) FROM v_doris"``
    must work end-to-end against a freshly-seeded local catalog without
    requiring MinIO credentials.
    """
    catalog_dir = tmp_path / "catalog"
    # Pre-seed the catalog with one L1 row so the count is non-zero and
    # the test catches breakages in the wiring rather than a no-op pass.
    from datorcloud.components.parquet_catalog_component import ParquetCatalogComponent
    import pandas as pd

    cat = ParquetCatalogComponent(metadata_base_uri=str(catalog_dir))
    cat.write_rows(
        "l1_experiment",
        pd.DataFrame(
            [
                {
                    "record_uid": "u1",
                    "dataset_id": "totalsegmentator",
                    "dataset_version": "v2",
                    "subject_id": "s0011",
                    "study_id": "",
                    "privacy_class": "public",
                    "license_spdx": "CC-BY-4.0",
                    "redistribution_ok": True,
                    "license_rule_version": "v1",
                    "share_alike_obligation": False,
                }
            ]
        ),
    )
    # The CLI builds a fresh orchestrator that points at the same
    # ``catalog_base_uri`` directory. We pass the catalog through a
    # monkeypatched factory so both orchestrators share state.
    real_build = cli._build_orchestrator

    def fake_build(args, *, require_minio=True):
        orch = real_build(args, require_minio=require_minio)
        orch.parquet_catalog = cat
        return orch

    monkeypatch.setattr(cli, "_build_orchestrator", fake_build)

    rc = cli.main(
        [
            "query",
            "--sql",
            "SELECT count(*) AS n FROM v_doris",
            "--catalog-base-uri",
            str(catalog_dir),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    # CSV output: "n\n1\n"
    assert "1" in captured.out
