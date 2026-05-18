"""Integration tests for :class:`DatorCloudOrchestrator` with fake services."""

from __future__ import annotations

import duckdb
import pytest

from datorcloud.components.metadata_generator_component import (
    MetadataGeneratorComponent,
)
from datorcloud.components.metadata_storage_component import (
    MetadataStorageComponent,
)
from datorcloud.components.minio_component import MinioObjectComponent
from datorcloud.components.query_component import QueryComponent
from datorcloud.components.retrieval_component import ObjectRetrievalComponent
from datorcloud.core import DatorCloudOrchestrator


@pytest.fixture
def orchestrator(fake_minio, tmp_path):
    minio = MinioObjectComponent(client=fake_minio)
    query = QueryComponent.__new__(QueryComponent)
    query.conn = duckdb.connect(":memory:")
    return DatorCloudOrchestrator(
        data_bucket="orx-datalake",
        metadata_bucket="orx-metadata",
        local_download_dir=str(tmp_path / "out"),
        minio_component=minio,
        metadata_generator=MetadataGeneratorComponent(),
        metadata_storage=MetadataStorageComponent(
            minio_component=minio, metadata_bucket="orx-metadata"
        ),
        query_component=query,
        retrieval_component=ObjectRetrievalComponent(
            minio_component=minio,
            query_component=query,
            local_base_dir=str(tmp_path / "out"),
        ),
    )


def test_full_pipeline(orchestrator, fake_minio, synthetic_dataset, tmp_path):
    dataset_paths = {"4dor-dataset": str(synthetic_dataset)}

    upload_results = orchestrator.upload_datasets(dataset_paths)
    assert len(upload_results["4dor-dataset"]) == 3
    assert "orx-datalake" in fake_minio.buckets

    metadata_csv = tmp_path / "metadata.csv"
    df = orchestrator.generate_and_upload_metadata(
        dataset_dirs=dataset_paths,
        output_file=str(metadata_csv),
        object_name="metadata.csv",
    )
    assert len(df) == 3
    assert "metadata.csv" in fake_minio.buckets["orx-metadata"]

    # The query component uses the local CSV directly via DuckDB.
    results = orchestrator.query_metadata(
        metadata_file=str(metadata_csv),
        filters={"camera_id": "camera01"},
    )
    assert len(results) == 2

    retrieved = orchestrator.retrieve_data(
        dataset="4dor-dataset",
        metadata_file=str(metadata_csv),
        camera_id="camera01",
        image_type="colorimage",
    )
    assert len(retrieved) == 1
    assert retrieved[0]["success"] is True
    assert (
        retrieved[0]["object_name"]
        == "4dor-dataset/experiment-1/camera01/colorimage/camera01_colorimage-000031.jpg"
    )
