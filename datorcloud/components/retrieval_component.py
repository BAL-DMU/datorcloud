"""Component that downloads objects from MinIO based on metadata queries."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .minio_component import MinioObjectComponent
from .query_component import QueryComponent

log = logging.getLogger(__name__)


class ObjectRetrievalComponent:
    """Component for retrieving data objects based on metadata queries."""

    def __init__(
        self,
        minio_component: MinioObjectComponent,
        query_component: QueryComponent,
        local_base_dir: str = "./retrieved_data",
    ) -> None:
        """Initialize the object retrieval component.

        Args:
            minio_component: MinIO component for downloading files.
            query_component: Query component for metadata queries.
            local_base_dir: Base directory for downloaded files.
        """
        self.minio_component = minio_component
        self.query_component = query_component
        self.local_base_dir = local_base_dir

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _normalize_object_key(*parts: str) -> str:
        """Join parts using POSIX separators and drop any ``.`` / empty segments.

        The metadata layer stores subfolders relative to each experiment root, and
        ``os.path.relpath`` returns ``"."`` for the experiment root itself. Joining
        naively would produce keys such as ``ds/exp/./file.jpg``. We normalize
        here so the MinIO key is always ``ds/exp/file.jpg``.
        """
        clean: List[str] = []
        for part in parts:
            if not part:
                continue
            sub = part.replace("\\", "/").strip("/")
            for piece in sub.split("/"):
                if piece and piece != ".":
                    clean.append(piece)
        return "/".join(clean)

    @staticmethod
    def _is_under_dataset_prefix(file_path: str, dataset: str) -> bool:
        normalized = file_path.replace("\\", "/").lstrip("/")
        return normalized.startswith(f"{dataset}/")

    # ---- public API ------------------------------------------------------

    def retrieve_objects(
        self,
        metadata_file: str,
        dataset: str,
        data_bucket: str = "orx-datalake",
        local_dir: Optional[str] = None,
        max_files: Optional[int] = None,
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve objects from MinIO based on a metadata query.

        Args:
            metadata_file: S3 path to the metadata CSV.
            dataset: Dataset name.
            data_bucket: Bucket containing the data.
            local_dir: Optional local directory override.
            max_files: Maximum number of files to retrieve.
            **filters: Additional filters to apply.

        Returns:
            List of dictionaries with information about retrieved files.
        """
        object_infos = self.query_component.get_object_paths(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=data_bucket,
            **filters,
        )

        if max_files is not None:
            object_infos = object_infos[:max_files]

        base_dir = local_dir if local_dir else self.local_base_dir
        downloaded: List[Dict[str, Any]] = []

        for info in object_infos:
            experiment = info.get("experiment", "")
            subfolder = info.get("subfolder", "")
            file_name = info.get("file_name", "")
            stored_path = info.get("object_name") or info.get("file_path", "")

            if stored_path and self._is_under_dataset_prefix(stored_path, dataset):
                object_name = stored_path.replace("\\", "/").lstrip("/")
            else:
                object_name = self._normalize_object_key(
                    dataset, experiment, subfolder, file_name
                )

            local_path = os.path.join(
                base_dir, dataset, experiment, *_split_subfolder(subfolder), file_name
            )

            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            success = self.minio_component.download_file(
                bucket_name=data_bucket,
                object_name=object_name,
                file_path=local_path,
            )
            if not success:
                log.warning(
                    "Failed to download object %s from bucket %s",
                    object_name,
                    data_bucket,
                )

            downloaded.append(
                {
                    "object_name": object_name,
                    "local_path": local_path,
                    "success": success,
                    "experiment": experiment,
                    "dataset": dataset,
                    "subfolder": subfolder,
                    "file_name": file_name,
                }
            )

        return downloaded

    def retrieve_experiment_data(
        self,
        metadata_file: str,
        dataset: str,
        experiment: str,
        data_bucket: str = "orx-datalake",
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve all data for a specific experiment."""
        filters["experiment"] = experiment
        return self.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=data_bucket,
            **filters,
        )

    def retrieve_camera_data(
        self,
        metadata_file: str,
        dataset: str,
        camera_id: str,
        data_bucket: str = "orx-datalake",
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve data for a specific camera."""
        filters["camera_id"] = camera_id
        return self.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=data_bucket,
            **filters,
        )


def _split_subfolder(subfolder: str) -> List[str]:
    """Split a ``subfolder`` value into clean path components.

    Drops empty and ``.`` segments to avoid ``dataset/exp/./file`` style paths.
    """
    if not subfolder:
        return []
    parts = subfolder.replace("\\", "/").split("/")
    return [p for p in parts if p and p != "."]


# Convenience re-export for tests / external consumers
join_object_key = ObjectRetrievalComponent._normalize_object_key
__all__ = ["ObjectRetrievalComponent", "join_object_key"]
