"""Unit tests for :class:`ObjectRetrievalComponent`."""

from __future__ import annotations

import os

import pytest

from datorcloud.components.retrieval_component import (
    ObjectRetrievalComponent,
    join_object_key,
)


class StubQueryComponent:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def get_object_paths(self, metadata_file, dataset, data_bucket, **filters):
        self.calls.append({"metadata_file": metadata_file, "dataset": dataset, "filters": filters})
        return list(self._rows)


def test_normalize_object_key_drops_dot_and_blank_segments():
    assert join_object_key("ds", "exp", ".", "file.jpg") == "ds/exp/file.jpg"
    assert join_object_key("ds", "", "sub", "file.jpg") == "ds/sub/file.jpg"
    assert (
        join_object_key("ds\\exp", "camera01/colorimage", "f.jpg")
        == "ds/exp/camera01/colorimage/f.jpg"
    )


def test_retrieve_objects_uses_stored_path_when_under_dataset_prefix(
    minio_component, fake_minio, tmp_path
):
    fake_minio.buckets["orx-datalake"] = {
        "4dor/exp-1/camera01/colorimage/file.jpg": b"DATA",
    }
    stub_query = StubQueryComponent(
        rows=[
            {
                "experiment": "exp-1",
                "full_path": "s3://orx-datalake/4dor/exp-1/camera01/colorimage/file.jpg",
                "object_name": "4dor/exp-1/camera01/colorimage/file.jpg",
                "file_path": "4dor/exp-1/camera01/colorimage/file.jpg",
                "subfolder": "camera01/colorimage",
                "file_name": "file.jpg",
            }
        ]
    )
    retrieval = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=stub_query,
        local_base_dir=str(tmp_path / "out"),
    )

    results = retrieval.retrieve_objects(
        metadata_file="s3://orx-metadata/metadata.csv",
        dataset="4dor",
        data_bucket="orx-datalake",
    )

    assert len(results) == 1
    record = results[0]
    assert record["success"] is True
    assert record["object_name"] == "4dor/exp-1/camera01/colorimage/file.jpg"
    expected = (
        tmp_path / "out" / "4dor" / "exp-1" / "camera01" / "colorimage" / "file.jpg"
    )
    assert os.path.exists(expected)
    assert expected.read_bytes() == b"DATA"


def test_retrieve_objects_rebuilds_key_when_path_lacks_dataset_prefix(
    minio_component, fake_minio, tmp_path
):
    fake_minio.buckets["orx-datalake"] = {
        "4dor/exp-1/camera01/colorimage/file.jpg": b"DATA",
    }
    stub_query = StubQueryComponent(
        rows=[
            {
                "experiment": "exp-1",
                "full_path": "s3://orx-datalake/exp-1/camera01/colorimage/file.jpg",
                "object_name": "exp-1/camera01/colorimage/file.jpg",
                "file_path": "exp-1/camera01/colorimage/file.jpg",
                "subfolder": "camera01/colorimage",
                "file_name": "file.jpg",
            }
        ]
    )
    retrieval = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=stub_query,
        local_base_dir=str(tmp_path / "out"),
    )

    results = retrieval.retrieve_objects(
        metadata_file="s3://orx-metadata/metadata.csv",
        dataset="4dor",
        data_bucket="orx-datalake",
    )
    assert results[0]["object_name"] == "4dor/exp-1/camera01/colorimage/file.jpg"


def test_retrieve_objects_respects_max_files(minio_component, fake_minio, tmp_path):
    fake_minio.buckets["orx-datalake"] = {
        f"4dor/exp-{i}/file.jpg": b"x" for i in range(5)
    }
    rows = [
        {
            "experiment": f"exp-{i}",
            "full_path": f"s3://orx-datalake/4dor/exp-{i}/file.jpg",
            "object_name": f"4dor/exp-{i}/file.jpg",
            "file_path": f"4dor/exp-{i}/file.jpg",
            "subfolder": "",
            "file_name": "file.jpg",
        }
        for i in range(5)
    ]
    retrieval = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=StubQueryComponent(rows),
        local_base_dir=str(tmp_path / "out"),
    )
    results = retrieval.retrieve_objects(
        metadata_file="meta",
        dataset="4dor",
        data_bucket="orx-datalake",
        max_files=2,
    )
    assert len(results) == 2


def test_retrieve_objects_marks_download_failures(minio_component, fake_minio, tmp_path):
    fake_minio.buckets["orx-datalake"] = {"4dor/exp-1/file.jpg": b"x"}
    fake_minio.fail_download_for.add("4dor/exp-1/file.jpg")
    retrieval = ObjectRetrievalComponent(
        minio_component=minio_component,
        query_component=StubQueryComponent(
            rows=[
                {
                    "experiment": "exp-1",
                    "full_path": "s3://orx-datalake/4dor/exp-1/file.jpg",
                    "object_name": "4dor/exp-1/file.jpg",
                    "file_path": "4dor/exp-1/file.jpg",
                    "subfolder": "",
                    "file_name": "file.jpg",
                }
            ]
        ),
        local_base_dir=str(tmp_path / "out"),
    )
    results = retrieval.retrieve_objects(
        metadata_file="meta", dataset="4dor", data_bucket="orx-datalake"
    )
    assert results[0]["success"] is False
