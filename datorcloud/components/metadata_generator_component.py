"""Component that walks a dataset directory tree and emits a metadata table."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)


class MetadataGeneratorComponent:
    """Component for generating and managing metadata from datasets and experiments."""

    # Pattern to extract a frame number from filenames such as
    # ``camera01_colorimage-000031.jpg`` -> 31.
    DEFAULT_FRAME_PATTERN = re.compile(r"-(\d+)\.")

    def __init__(self, frame_pattern: Optional[re.Pattern] = None) -> None:
        self.frame_pattern = frame_pattern or self.DEFAULT_FRAME_PATTERN

    def extract_frame_number(self, filename: str) -> Optional[int]:
        """Extract the frame number from a filename."""
        match = self.frame_pattern.search(filename)
        if match:
            return int(match.group(1))
        return None

    def extract_camera_info(
        self, path_parts: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract camera id and image type from path components."""
        camera_id: Optional[str] = None
        image_type: Optional[str] = None
        for part in path_parts:
            if part.startswith("camera") or part.startswith("kinect"):
                camera_id = part
            elif part in {"colorimage", "depthimage"}:
                image_type = part
        return camera_id, image_type

    def collect_dataset_metadata(
        self, dataset_name: str, base_dir: str
    ) -> List[Dict[str, Any]]:
        """Collect metadata for a single dataset directory."""
        records: List[Dict[str, Any]] = []
        if not os.path.exists(base_dir):
            log.warning("Dataset directory '%s' does not exist.", base_dir)
            return records

        for experiment in os.listdir(base_dir):
            experiment_path = os.path.join(base_dir, experiment)
            if not os.path.isdir(experiment_path):
                continue

            for root, _dirs, files in os.walk(experiment_path):
                subfolder_rel = os.path.relpath(root, experiment_path)
                if subfolder_rel == ".":
                    subfolder_rel = ""

                path_parts = (
                    subfolder_rel.split(os.sep) if subfolder_rel else []
                )
                camera_id, image_type = self.extract_camera_info(path_parts)

                for file_name in files:
                    # Build a POSIX-style file_path relative to the dataset root
                    # so it can be combined with ``s3://bucket/{dataset}/...``.
                    rel_parts = [dataset_name, experiment]
                    if subfolder_rel:
                        rel_parts.extend(subfolder_rel.split(os.sep))
                    rel_parts.append(file_name)
                    file_path = "/".join(p for p in rel_parts if p)

                    records.append(
                        {
                            "dataset": dataset_name,
                            "experiment": experiment,
                            "subfolder": subfolder_rel.replace(os.sep, "/"),
                            "file_name": file_name,
                            "file_path": file_path,
                            "file_format": os.path.splitext(file_name)[1]
                            .lstrip(".")
                            .lower(),
                            "camera_id": camera_id,
                            "image_type": image_type,
                            "frame_number": self.extract_frame_number(file_name),
                        }
                    )
        return records

    def generate_metadata(
        self,
        dataset_dirs: Dict[str, str],
        output_file: Optional[str] = None,
    ) -> pd.DataFrame:
        """Generate metadata for multiple datasets.

        Args:
            dataset_dirs: Mapping of dataset names to dataset root directories.
            output_file: Optional path to write the resulting CSV.

        Returns:
            A DataFrame with one row per file discovered.
        """
        all_metadata: List[Dict[str, Any]] = []
        for dataset_name, base_dir in dataset_dirs.items():
            all_metadata.extend(self.collect_dataset_metadata(dataset_name, base_dir))

        metadata_df = pd.DataFrame(all_metadata)

        if output_file:
            parent = os.path.dirname(output_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            metadata_df.to_csv(output_file, index=False)
            log.info("Metadata file '%s' generated successfully.", output_file)

        return metadata_df
