"""Unit tests for :class:`MetadataStorageComponent`."""

from __future__ import annotations

import os

import pandas as pd

from datorcloud.components.metadata_generator_component import (
    MetadataGeneratorComponent,
)
from datorcloud.components.metadata_storage_component import (
    MetadataStorageComponent,
)


def test_store_metadata_writes_and_uploads(minio_component, fake_minio, tmp_path):
    storage = MetadataStorageComponent(
        minio_component=minio_component, metadata_bucket="orx-metadata"
    )
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    local = tmp_path / "out" / "metadata.csv"
    assert storage.store_metadata(df, str(local), object_name="metadata.csv")
    assert local.exists()
    assert "metadata.csv" in fake_minio.buckets["orx-metadata"]


def test_create_metadata_and_store_end_to_end(
    minio_component, fake_minio, synthetic_dataset, tmp_path
):
    storage = MetadataStorageComponent(
        minio_component=minio_component, metadata_bucket="orx-metadata"
    )
    df = storage.create_metadata_and_store(
        metadata_generator_component=MetadataGeneratorComponent(),
        dataset_dirs={"4dor-dataset": str(synthetic_dataset)},
        local_file_path=str(tmp_path / "metadata.csv"),
        object_name="metadata.csv",
    )
    assert not df.empty
    assert "metadata.csv" in fake_minio.buckets["orx-metadata"]
    assert os.path.exists(tmp_path / "metadata.csv")
