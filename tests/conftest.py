"""Shared pytest fixtures for the DatorCloud test suite."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fake MinIO client
# ---------------------------------------------------------------------------


class FakeS3Error(Exception):
    """Stand-in for ``minio.error.S3Error`` used by the fake client."""


@dataclass
class FakeMinioClient:
    """In-memory MinIO replacement.

    Mimics just enough of ``minio.Minio`` for the component layer:
    ``bucket_exists``, ``make_bucket``, ``fput_object``, ``fget_object``,
    ``stat_object``.
    """

    buckets: Dict[str, Dict[str, bytes]] = field(default_factory=dict)
    fail_upload_for: set = field(default_factory=set)
    fail_download_for: set = field(default_factory=set)

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.setdefault(bucket, {})

    def fput_object(self, bucket: str, object_name: str, file_path: str) -> None:
        if object_name in self.fail_upload_for:
            raise FakeS3Error(f"forced failure for {object_name}")
        with open(file_path, "rb") as fh:
            self.buckets.setdefault(bucket, {})[object_name] = fh.read()

    def fget_object(self, bucket: str, object_name: str, file_path: str) -> None:
        if object_name in self.fail_download_for:
            raise FakeS3Error(f"forced failure for {object_name}")
        data = self.buckets.get(bucket, {}).get(object_name)
        if data is None:
            raise FakeS3Error(f"NoSuchKey: {bucket}/{object_name}")
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "wb") as fh:
            fh.write(data)

    def stat_object(self, bucket: str, object_name: str) -> Dict[str, Any]:
        if object_name not in self.buckets.get(bucket, {}):
            raise FakeS3Error("not found")
        return {"size": len(self.buckets[bucket][object_name])}

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = True) -> List[str]:
        return [
            name for name in self.buckets.get(bucket, {}).keys() if name.startswith(prefix)
        ]


# Patch ``minio.error.S3Error`` so the component code that catches it also catches
# our :class:`FakeS3Error` during tests.
@pytest.fixture(autouse=True)
def _patch_s3error(monkeypatch):
    import minio.error

    monkeypatch.setattr(minio.error, "S3Error", FakeS3Error)
    import datorcloud.components.minio_component as mc

    monkeypatch.setattr(mc, "S3Error", FakeS3Error)


@pytest.fixture
def fake_minio() -> FakeMinioClient:
    return FakeMinioClient()


@pytest.fixture
def minio_component(fake_minio):
    from datorcloud.components.minio_component import MinioObjectComponent

    return MinioObjectComponent(client=fake_minio)


# ---------------------------------------------------------------------------
# Synthetic dataset trees
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_dataset(tmp_path):
    """Create a small dataset tree on disk and return its root path.

    Layout::

        tmp_path/datasets/4dor-dataset/
            experiment-1/
                camera01/colorimage/camera01_colorimage-000031.jpg
                camera01/depthimage/camera01_depthimage-000031.tiff
                camera02/colorimage/camera02_colorimage-000061.jpg
    """
    root = tmp_path / "datasets" / "4dor-dataset"
    files = [
        "experiment-1/camera01/colorimage/camera01_colorimage-000031.jpg",
        "experiment-1/camera01/depthimage/camera01_depthimage-000031.tiff",
        "experiment-1/camera02/colorimage/camera02_colorimage-000061.jpg",
    ]
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rel.encode("utf-8"))
    return root
