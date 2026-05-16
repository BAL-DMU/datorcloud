"""Tests for the Dagster integration.

Skipped automatically when ``dagster`` is not installed in the environment.
"""

import pytest

dagster = pytest.importorskip("dagster")

from datorcloud.dagster import (  # noqa: E402
    DatorCloudResource,
    UploadDatasetsConfig,
    component_assets,
    upload_datasets,
)


@pytest.fixture
def patched_minio_class(monkeypatch, fake_minio):
    """Force every new :class:`minio.Minio` instance to point at the fake."""

    def _factory(*_args, **_kwargs):
        return fake_minio

    import minio as minio_pkg

    monkeypatch.setattr(minio_pkg, "Minio", _factory)
    import datorcloud.components.minio_component as mc

    monkeypatch.setattr(mc, "Minio", _factory)
    return fake_minio


def test_resource_builds_components(patched_minio_class):
    resource = DatorCloudResource(
        minio_endpoint="minio:9090",
        minio_access_key="test",
        minio_secret_key="test",
        data_bucket="orx-datalake",
    )
    assert resource.minio.client is patched_minio_class
    assert resource.metadata_generator is not None
    assert resource.metadata_storage.metadata_bucket == "orx-metadata"


def test_component_assets_are_dagster_assets():
    from dagster import AssetsDefinition

    for asset_def in component_assets:
        assert isinstance(asset_def, AssetsDefinition)


def test_upload_datasets_materializes(patched_minio_class, synthetic_dataset, tmp_path):
    from dagster import materialize

    resource = DatorCloudResource(
        minio_access_key="test",
        minio_secret_key="test",
        data_bucket="orx-datalake",
    )

    result = materialize(
        [upload_datasets],
        resources={"datorcloud": resource},
        run_config={
            "ops": {
                "upload_datasets": {
                    "config": {
                        "dataset_paths": {"4dor-dataset": str(synthetic_dataset)},
                    }
                }
            }
        },
    )
    assert result.success
    output = result.output_for_node("upload_datasets")
    assert "4dor-dataset" in output
    assert len(output["4dor-dataset"]) == 3
