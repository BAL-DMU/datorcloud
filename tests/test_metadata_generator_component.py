"""Unit tests for :class:`MetadataGeneratorComponent`."""

from __future__ import annotations

import pandas as pd

from datorcloud.components.metadata_generator_component import (
    MetadataGeneratorComponent,
)


def test_extract_frame_number():
    gen = MetadataGeneratorComponent()
    assert gen.extract_frame_number("camera01_colorimage-000031.jpg") == 31
    assert gen.extract_frame_number("kinect_xx_colorimage-002000.jpg") == 2000
    assert gen.extract_frame_number("no_frame.jpg") is None


def test_extract_camera_info():
    gen = MetadataGeneratorComponent()
    cam, img = gen.extract_camera_info(["camera01", "colorimage"])
    assert cam == "camera01"
    assert img == "colorimage"

    cam, img = gen.extract_camera_info(["kinect_000385500312", "depthimage"])
    assert cam == "kinect_000385500312"
    assert img == "depthimage"

    cam, img = gen.extract_camera_info([])
    assert cam is None and img is None


def test_generate_metadata_creates_records(synthetic_dataset, tmp_path):
    gen = MetadataGeneratorComponent()
    out_file = tmp_path / "metadata.csv"
    df = gen.generate_metadata(
        dataset_dirs={"4dor-dataset": str(synthetic_dataset)},
        output_file=str(out_file),
    )
    assert len(df) == 3
    assert set(df.columns) >= {
        "dataset",
        "experiment",
        "subfolder",
        "file_name",
        "file_path",
        "file_format",
        "camera_id",
        "image_type",
        "frame_number",
    }
    # file_path must be the full object key, POSIX separators only.
    assert all(p.startswith("4dor-dataset/experiment-1/") for p in df["file_path"])
    assert all("\\" not in p for p in df["file_path"])
    assert out_file.exists()
    reloaded = pd.read_csv(out_file)
    assert len(reloaded) == 3


def test_generate_metadata_missing_dir_returns_empty(tmp_path):
    gen = MetadataGeneratorComponent()
    df = gen.generate_metadata({"missing": str(tmp_path / "nope")})
    assert df.empty
