"""Unit tests for :class:`MinioObjectComponent`."""

from __future__ import annotations

import os


def test_ensure_bucket_creates_when_missing(minio_component, fake_minio):
    assert minio_component.ensure_bucket_exists("orx-datalake") is True
    assert "orx-datalake" in fake_minio.buckets


def test_ensure_bucket_idempotent(minio_component, fake_minio):
    minio_component.ensure_bucket_exists("orx-datalake")
    minio_component.ensure_bucket_exists("orx-datalake")
    assert list(fake_minio.buckets.keys()) == ["orx-datalake"]


def test_upload_directory_records_each_file(minio_component, fake_minio, synthetic_dataset):
    results = minio_component.upload_directory(
        local_directory=str(synthetic_dataset),
        bucket_name="orx-datalake",
        prefix="4dor-dataset",
    )
    assert len(results) == 3
    statuses = [r["status"] for r in results]
    assert statuses == ["success", "success", "success"]
    keys = sorted(fake_minio.buckets["orx-datalake"].keys())
    assert all(k.startswith("4dor-dataset/experiment-1/") for k in keys)
    # POSIX separators in keys, even on Windows.
    assert all("\\" not in k for k in keys)


def test_upload_directory_reports_failures(minio_component, fake_minio, synthetic_dataset):
    target = "4dor-dataset/experiment-1/camera01/colorimage/camera01_colorimage-000031.jpg"
    fake_minio.fail_upload_for.add(target)
    results = minio_component.upload_directory(
        local_directory=str(synthetic_dataset),
        bucket_name="orx-datalake",
        prefix="4dor-dataset",
    )
    failed = [r for r in results if r["status"] == "error"]
    assert len(failed) == 1
    assert failed[0]["object_name"] == target


def test_upload_and_download_round_trip(minio_component, fake_minio, tmp_path):
    src = tmp_path / "src.txt"
    src.write_bytes(b"hello")
    minio_component.upload_file("bucket", "subdir/file.txt", str(src))

    dst = tmp_path / "out" / "file.txt"
    assert minio_component.download_file("bucket", "subdir/file.txt", str(dst))
    assert dst.read_bytes() == b"hello"
    assert os.path.exists(dst)


def test_download_missing_returns_false(minio_component):
    assert minio_component.download_file("bucket", "nope", "/tmp/x") is False
