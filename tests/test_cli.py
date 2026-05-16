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
