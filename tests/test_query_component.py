"""Unit tests for :class:`QueryComponent` using an in-process DuckDB connection."""

from __future__ import annotations

import duckdb
import pytest

from datorcloud.components.query_component import QueryComponent


@pytest.fixture
def csv_metadata(tmp_path):
    """A small metadata CSV stored on disk; queried via ``read_csv_auto``."""
    path = tmp_path / "metadata.csv"
    path.write_text(
        "dataset,experiment,subfolder,file_name,file_path,camera_id,image_type,frame_number\n"
        "4dor,exp-1,camera01/colorimage,camera01_colorimage-000031.jpg,4dor/exp-1/camera01/colorimage/camera01_colorimage-000031.jpg,camera01,colorimage,31\n"
        "4dor,exp-1,camera02/colorimage,camera02_colorimage-000061.jpg,4dor/exp-1/camera02/colorimage/camera02_colorimage-000061.jpg,camera02,colorimage,61\n"
        "4dor,exp-2,camera01/depthimage,camera01_depthimage-000031.tiff,4dor/exp-2/camera01/depthimage/camera01_depthimage-000031.tiff,camera01,depthimage,31\n"
    )
    return path


@pytest.fixture
def query_component():
    # Use a real in-memory DuckDB connection but skip the network-bound
    # httpfs/S3 configuration that would normally require live MinIO.
    conn = duckdb.connect(":memory:")
    qc = QueryComponent.__new__(QueryComponent)
    qc.conn = conn
    return qc


def test_build_where_clause_strings_lists_and_numbers():
    where = QueryComponent._build_where_clause(
        {"camera_id": "camera01", "frame_number": 31, "experiment": ["a", "b"]}
    )
    assert "camera_id = 'camera01'" in where
    assert "frame_number = 31" in where
    assert "experiment IN ('a', 'b')" in where
    assert where.startswith(" WHERE ")


def test_build_where_clause_escapes_single_quotes():
    where = QueryComponent._build_where_clause({"name": "O'Connor"})
    assert "name = 'O''Connor'" in where


def test_query_metadata_filters_and_limits(query_component, csv_metadata):
    df = query_component.query_metadata(
        metadata_file=str(csv_metadata),
        filters={"camera_id": "camera01"},
    )
    assert len(df) == 2
    assert set(df["experiment"]) == {"exp-1", "exp-2"}

    df = query_component.query_metadata(
        metadata_file=str(csv_metadata),
        filters={"camera_id": "camera01", "image_type": "colorimage"},
        limit=1,
    )
    assert len(df) == 1


def test_get_object_paths_returns_expected_keys(query_component, csv_metadata):
    rows = query_component.get_object_paths(
        metadata_file=str(csv_metadata),
        dataset="4dor",
        data_bucket="orx-datalake",
        camera_id="camera01",
    )
    assert len(rows) == 2
    for row in rows:
        assert row["object_name"].startswith("4dor/")
        assert row["full_path"].startswith("s3://orx-datalake/4dor/")
