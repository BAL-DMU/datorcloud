"""High-level orchestrator that wires every DatorCloud component together.

Phase 1 of the DORIS integration plan adds the formal ``(I, C, Q, F)``
operators -- ``ingest``, ``snapshot_cohort`` (+ ``create_eval_set``),
``query``, and ``fetch`` -- on top of the existing legacy methods. The
legacy methods (``upload_datasets``, ``generate_and_upload_metadata``,
``query_metadata``, ``retrieve_data``) continue to work unchanged so
already-deployed callers do not break.

The ``from_env`` factory and ``.env`` contract are preserved verbatim
(STEP_BY_STEP_PLAN.md §3 step 1.3 gate).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from ..components.hf_publisher_component import (
    DEFAULT_ALLOWED_LICENSES,
    HFPublisherComponent,
    HubBackend,
    LocalFilesystemHub,
    PublishPolicy,
    PublishResult,
)
from ..components.metadata_generator_component import MetadataGeneratorComponent
from ..components.metadata_storage_component import MetadataStorageComponent
from ..components.minio_component import MinioObjectComponent
from ..components.parquet_catalog_component import ParquetCatalogComponent
from ..components.query_component import QueryComponent
from ..components.retrieval_component import ObjectRetrievalComponent
from ..snapshots import (
    EvalSet,
    Snapshot,
    create_eval_set as _create_eval_set,
    load_snapshot_payload,
    snapshot_cohort as _snapshot_cohort,
)

log = logging.getLogger(__name__)

DEFAULT_DATA_BUCKET = "orx-datalake"
DEFAULT_METADATA_BUCKET = "orx-metadata"
DEFAULT_DATA_LAKE_DIR = "./data_lake"
DEFAULT_RETRIEVED_DIR = "./retrieved_data"
DEFAULT_REGION = "us-east-1"

# Default parquet catalog root used when the caller does not pass one
# explicitly. Resolved relative to ``local_data_dir``.
DEFAULT_PARQUET_CATALOG_SUBDIR = "catalog"


class DatorCloudOrchestrator:
    """Main orchestrator class for DatorCloud operations.

    Coordinates the workflow between every component without forcing callers
    to assemble them by hand.

    For environment-driven construction (the recommended path for the CLI
    and notebook usage), prefer :meth:`from_env`, which reads connection
    and storage settings from the project ``.env``.
    """

    def __init__(
        self,
        minio_endpoint: Optional[str] = None,
        minio_access_key: Optional[str] = None,
        minio_secret_key: Optional[str] = None,
        minio_secure: bool = False,
        s3_region: str = DEFAULT_REGION,
        data_bucket: str = DEFAULT_DATA_BUCKET,
        metadata_bucket: str = DEFAULT_METADATA_BUCKET,
        local_data_dir: str = DEFAULT_DATA_LAKE_DIR,
        local_download_dir: str = DEFAULT_RETRIEVED_DIR,
        duckdb_extension_path: Optional[str] = None,
        minio_component: Optional[MinioObjectComponent] = None,
        metadata_generator: Optional[MetadataGeneratorComponent] = None,
        metadata_storage: Optional[MetadataStorageComponent] = None,
        query_component: Optional[QueryComponent] = None,
        retrieval_component: Optional[ObjectRetrievalComponent] = None,
        parquet_catalog: Optional[ParquetCatalogComponent] = None,
        catalog_base_uri: Optional[str] = None,
    ) -> None:
        """Initialize the orchestrator.

        Each component can be injected explicitly (handy for tests). When a
        component is not provided, a default one is built from the configuration
        parameters — which means ``minio_access_key`` and ``minio_secret_key``
        become **required** (since the underlying components no longer ship
        hard-coded credentials).
        """
        self.minio_component = minio_component or MinioObjectComponent(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure,
        )
        self.metadata_generator = (
            metadata_generator or MetadataGeneratorComponent()
        )
        self.query_component = query_component or QueryComponent(
            s3_region=s3_region,
            s3_endpoint=minio_endpoint,
            s3_access_key=minio_access_key,
            s3_secret_key=minio_secret_key,
            s3_use_ssl=minio_secure,
            duckdb_extension_path=duckdb_extension_path,
        )
        self.metadata_storage = metadata_storage or MetadataStorageComponent(
            minio_component=self.minio_component,
            metadata_bucket=metadata_bucket,
        )
        self.retrieval_component = (
            retrieval_component
            or ObjectRetrievalComponent(
                minio_component=self.minio_component,
                query_component=self.query_component,
                local_base_dir=local_download_dir,
            )
        )

        self.data_bucket = data_bucket
        self.metadata_bucket = metadata_bucket
        self.local_data_dir = local_data_dir
        self.local_download_dir = local_download_dir
        self._last_metadata_file: Optional[str] = None

        # Phase 1 -- L1-L4 Parquet catalog. Constructed lazily so legacy
        # callers (which never touch the catalog) do not pay the DuckDB
        # in-memory setup cost.
        if parquet_catalog is not None:
            self.parquet_catalog: Optional[ParquetCatalogComponent] = parquet_catalog
        elif catalog_base_uri is not None:
            self.parquet_catalog = ParquetCatalogComponent(
                metadata_base_uri=catalog_base_uri,
                minio_component=self.minio_component,
                metadata_bucket=metadata_bucket,
            )
        else:
            self.parquet_catalog = None
        self._catalog_base_uri = catalog_base_uri

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, **overrides: Any) -> "DatorCloudOrchestrator":
        """Build an orchestrator from environment variables.

        Reads (and loads ``.env`` first if ``python-dotenv`` is available):

        - ``S3_ENDPOINT``, ``S3_ACCESS_KEY``, ``S3_SECRET_KEY``
        - ``S3_USE_SSL``, ``S3_REGION``
        - ``DATA_LAKE_PATH``, ``RETRIEVED_DATA_PATH``
        - ``DUCKDB_HTTPFS_EXTENSION_PATH`` (passed through to QueryComponent)

        ``overrides`` are forwarded to ``__init__`` and take precedence over
        the environment.

        Raises:
            RuntimeError: when ``S3_ACCESS_KEY`` or ``S3_SECRET_KEY`` is
                missing and no override is supplied.
        """
        try:
            from dotenv import load_dotenv  # type: ignore[import-untyped]

            load_dotenv()
        except ImportError:
            pass

        endpoint = os.environ.get("S3_ENDPOINT", "minio:9090")
        endpoint = endpoint.replace("http://", "").replace("https://", "")

        access_key = os.environ.get("S3_ACCESS_KEY")
        secret_key = os.environ.get("S3_SECRET_KEY")
        if "minio_access_key" not in overrides and not access_key:
            raise RuntimeError(
                "S3_ACCESS_KEY is not set. Add it to your .env or pass "
                "`minio_access_key=` to DatorCloudOrchestrator.from_env()."
            )
        if "minio_secret_key" not in overrides and not secret_key:
            raise RuntimeError(
                "S3_SECRET_KEY is not set. Add it to your .env or pass "
                "`minio_secret_key=` to DatorCloudOrchestrator.from_env()."
            )

        kwargs: Dict[str, Any] = dict(
            minio_endpoint=endpoint,
            minio_access_key=access_key,
            minio_secret_key=secret_key,
            minio_secure=os.environ.get("S3_USE_SSL", "false").lower() == "true",
            s3_region=os.environ.get("S3_REGION", DEFAULT_REGION),
            local_data_dir=os.environ.get("DATA_LAKE_PATH", DEFAULT_DATA_LAKE_DIR),
            local_download_dir=os.environ.get(
                "RETRIEVED_DATA_PATH", DEFAULT_RETRIEVED_DIR
            ),
            duckdb_extension_path=os.environ.get("DUCKDB_HTTPFS_EXTENSION_PATH"),
            catalog_base_uri=os.environ.get("DATORCLOUD_CATALOG_URI"),
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    # ------------------------------------------------------------------
    # Workflow entry points
    # ------------------------------------------------------------------

    def upload_datasets(
        self,
        dataset_paths: Dict[str, str],
        bucket_name: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Upload one or more dataset directories to MinIO."""
        target_bucket = bucket_name or self.data_bucket
        self.minio_component.ensure_bucket_exists(target_bucket)

        results: Dict[str, List[Dict[str, Any]]] = {}
        for dataset_name, dataset_path in dataset_paths.items():
            if not os.path.exists(dataset_path):
                log.warning("Dataset path '%s' does not exist.", dataset_path)
                results[dataset_name] = []
                continue
            results[dataset_name] = self.minio_component.upload_directory(
                local_directory=dataset_path,
                bucket_name=target_bucket,
                prefix=dataset_name,
            )
        return results

    def generate_and_upload_metadata(
        self,
        dataset_dirs: Dict[str, str],
        output_file: str = "metadata.csv",
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None,
    ) -> pd.DataFrame:
        """Generate metadata for datasets and upload the CSV to MinIO."""
        return self.metadata_storage.create_metadata_and_store(
            metadata_generator_component=self.metadata_generator,
            dataset_dirs=dataset_dirs,
            local_file_path=output_file,
            bucket_name=bucket_name,
            object_name=object_name,
        )

    def query_metadata(
        self,
        metadata_file: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Query metadata from the metadata store."""
        if metadata_file is None:
            metadata_file = f"s3://{self.metadata_bucket}/metadata.csv"

        self._last_metadata_file = metadata_file
        return self.query_component.query_metadata(
            metadata_file=metadata_file,
            filters=filters,
            limit=limit,
        )

    def retrieve_data(
        self,
        dataset: str,
        metadata_file: Optional[str] = None,
        max_files: Optional[int] = None,
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve data based on a metadata query."""
        if metadata_file is None:
            metadata_file = (
                self._last_metadata_file
                or f"s3://{self.metadata_bucket}/metadata.csv"
            )
        return self.retrieval_component.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=self.data_bucket,
            max_files=max_files,
            **filters,
        )

    def retrieve_experiment(
        self,
        dataset: str,
        experiment: str,
        metadata_file: Optional[str] = None,
        **filters: Any,
    ) -> List[Dict[str, Any]]:
        """Retrieve all data for a specific experiment."""
        if metadata_file is None:
            metadata_file = (
                self._last_metadata_file
                or f"s3://{self.metadata_bucket}/metadata.csv"
            )
        return self.retrieval_component.retrieve_experiment_data(
            metadata_file=metadata_file,
            dataset=dataset,
            experiment=experiment,
            data_bucket=self.data_bucket,
            **filters,
        )

    # ------------------------------------------------------------------
    # Phase 1 -- formal (I, C, Q, F) operators
    #
    # These work against the L1-L4 Parquet catalog. They throw a clear
    # RuntimeError if no catalog is wired in, so legacy callers cannot
    # accidentally bypass the new layered model.
    # ------------------------------------------------------------------

    def _require_catalog(self) -> ParquetCatalogComponent:
        if self.parquet_catalog is None:
            raise RuntimeError(
                "Catalog operators (ingest/query/fetch/snapshot_cohort) "
                "require a parquet_catalog. Pass `catalog_base_uri=...` "
                "to DatorCloudOrchestrator(...) or set the "
                "DATORCLOUD_CATALOG_URI environment variable before "
                "calling from_env()."
            )
        return self.parquet_catalog

    # ---- I -----------------------------------------------------------

    def ingest(self, layer: str, df: pd.DataFrame) -> int:
        """**I** -- upsert rows into the named L1-L4 catalog layer.

        Returns the number of rows written. The layer name matches the
        DDL table name (``l1_experiment``, ``l2_sensor``, ``l3_annotation``,
        ``l1_processing``, ``l1_citations``).
        """
        return self._require_catalog().write_rows(layer, df)

    # ---- Q -----------------------------------------------------------

    def query(
        self,
        *,
        sql: Optional[str] = None,
        view: str = "v_doris",
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """**Q** -- formal query operator over the L1-L4 views.

        Two equivalent call styles:

        1. ``query(sql="SELECT ... FROM v_doris WHERE ...")`` -- raw SQL.
        2. ``query(view="v_doris", filters={"modality": "CT"})`` -- the
           thin wrapper API. Both return the same DataFrame for
           equivalent predicates (integration-test assertion f).
        """
        catalog = self._require_catalog()
        if sql is None:
            where = QueryComponent._build_where_clause(filters or {})
            sql = f"SELECT * FROM {view}{where}"
            if limit is not None:
                sql += f" LIMIT {int(limit)}"
        return catalog.query(sql)

    # ---- C -----------------------------------------------------------

    def snapshot_cohort(
        self,
        *,
        dataset_id: str,
        predicate_sql: Optional[str] = None,
        snapshot_date: Optional[str] = None,
    ) -> Snapshot:
        """**C** -- freeze a cohort identity into ``l4_cohort_snapshot``.

        See :func:`datorcloud.snapshots.snapshot_cohort` for the freeze
        semantics. ``catalog_sha256`` is stable across reruns even after
        ``l2_sensor.converted_uri`` mutations.
        """
        return _snapshot_cohort(
            self._require_catalog(),
            dataset_id=dataset_id,
            predicate_sql=predicate_sql,
            snapshot_date=snapshot_date,
        )

    def create_eval_set(
        self,
        *,
        eval_set_id: str,
        snapshot_id: str,
        annotator_columns: Sequence[str],
        target_labels: Sequence[str],
        inter_observer_quantiles: Optional[Sequence[float]] = None,
        notes: Optional[str] = None,
    ) -> EvalSet:
        """Attach a new ``l4_eval_set`` row to *snapshot_id* (per I3)."""
        return _create_eval_set(
            self._require_catalog(),
            eval_set_id=eval_set_id,
            snapshot_id=snapshot_id,
            annotator_columns=annotator_columns,
            target_labels=target_labels,
            inter_observer_quantiles=inter_observer_quantiles,
            notes=notes,
        )

    # ---- F -----------------------------------------------------------

    def fetch(
        self,
        *,
        snapshot_id: str,
        dest: str,
        with_blobs: bool = False,
    ) -> Dict[str, Any]:
        """**F** -- materialise a snapshot's MIRO tree under *dest*.

        Phase 1 writes the frozen catalog payload + a deterministic
        ``manifest.json`` summary; Phase 2 will add raw / converted blob
        downloads through :class:`MinioObjectComponent` when
        ``with_blobs=True``.

        Returns a result dict with ``snapshot_id``, ``manifest_path``,
        ``n_records``, ``catalog_sha256``, and a per-record
        ``records`` listing. Two consecutive calls into different dest
        directories produce byte-identical manifests (integration-test
        assertion d, Phase 1 share).
        """
        catalog = self._require_catalog()
        info = catalog.query(
            "SELECT catalog_sha256, n_records, predicate_sql FROM l4_cohort_snapshot "
            "WHERE snapshot_id = ?",
            params=[snapshot_id],
        )
        if info.empty:
            raise KeyError(f"snapshot not found: {snapshot_id!r}")
        meta = info.iloc[0].to_dict()

        payload = load_snapshot_payload(catalog, snapshot_id)
        dest_path = Path(dest) / snapshot_id
        dest_path.mkdir(parents=True, exist_ok=True)

        records: List[Dict[str, Any]] = []
        downloaded: List[Dict[str, Any]] = []
        if not payload.empty and "layer" in payload.columns:
            l1 = payload[payload["layer"] == "l1_experiment"]
            for _, row in l1.iterrows():
                rec = {
                    "record_uid": row["record_uid"],
                    "dataset_id": row["dataset_id"],
                    "dataset_version": row["dataset_version"],
                    "subject_id": row["subject_id"],
                    "study_id": row.get("study_id", ""),
                }
                records.append(rec)
                if with_blobs:
                    downloaded.extend(
                        self._fetch_record_blobs(payload, rec, dest_path)
                    )

        manifest = {
            "snapshot_id": snapshot_id,
            "catalog_sha256": meta["catalog_sha256"],
            "n_records": int(meta["n_records"]),
            "predicate_sql": meta.get("predicate_sql"),
            "miro_layout": "<dataset_id>/<subject_id>/image.nii.gz "
            "+ seg/<label>.nii.gz + manifest.json",
            "records": sorted(records, key=lambda r: r["record_uid"]),
        }
        manifest_path = dest_path / "manifest.json"
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        manifest_path.write_bytes(manifest_bytes)

        return {
            "snapshot_id": snapshot_id,
            "manifest_path": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "n_records": int(meta["n_records"]),
            "catalog_sha256": meta["catalog_sha256"],
            "records": records,
            "downloaded": downloaded,
        }

    def _fetch_record_blobs(
        self,
        payload: pd.DataFrame,
        record: Dict[str, Any],
        dest_root: Path,
    ) -> List[Dict[str, Any]]:
        """Download (when MinIO is wired) raw/converted/mask blobs for *record*."""
        results: List[Dict[str, Any]] = []
        rec_uid = record["record_uid"]
        subject_dir = (
            dest_root
            / str(record["dataset_id"])
            / str(record["subject_id"])
        )
        subject_dir.mkdir(parents=True, exist_ok=True)

        l2 = payload[(payload["layer"] == "l2_sensor") & (payload["record_uid"] == rec_uid)]
        for _, row in l2.iterrows():
            for col, sub in (("raw_uri", "image"), ("converted_uri", "image_converted")):
                uri = row.get(col)
                if not uri:
                    continue
                key = self._object_key_from_uri(uri)
                if key is None:
                    continue
                local = subject_dir / f"{sub}_{row['modality']}_{row['sequence'] or 'na'}.nii.gz"
                ok = self.minio_component.download_file(self.data_bucket, key, str(local))
                results.append({"record_uid": rec_uid, "local_path": str(local), "success": ok})

        l3 = payload[(payload["layer"] == "l3_annotation") & (payload["record_uid"] == rec_uid)]
        seg_dir = subject_dir / "seg"
        for _, row in l3.iterrows():
            uri = row.get("mask_uri")
            if not uri:
                continue
            key = self._object_key_from_uri(uri)
            if key is None:
                continue
            seg_dir.mkdir(parents=True, exist_ok=True)
            local = seg_dir / f"{row['label_canonical']}.nii.gz"
            ok = self.minio_component.download_file(self.data_bucket, key, str(local))
            results.append({"record_uid": rec_uid, "local_path": str(local), "success": ok})
        return results

    @staticmethod
    def _object_key_from_uri(uri: str) -> Optional[str]:
        """Strip an ``s3://bucket/`` prefix and return the object key, or None."""
        if not uri or not uri.startswith("s3://"):
            return None
        rest = uri[len("s3://"):]
        slash = rest.find("/")
        if slash < 0:
            return None
        return rest[slash + 1:]

    # ------------------------------------------------------------------
    # Phase 3 -- Hugging Face delivery
    #
    # Per STEP_BY_STEP_PLAN.md §5 (steps 3.1-3.6) DatorCloud is the
    # uploader. ``publish_to_hub`` is the canonical egress entry point;
    # it consumes an L4 snapshot and a target hub-id and writes objects
    # + L1-L4 Parquet sidecars + dataset card through the pluggable
    # ``HubBackend`` abstraction.
    # ------------------------------------------------------------------

    def publish_to_hub(
        self,
        *,
        snapshot_id: str,
        hub_id: str,
        allowed_licenses: Sequence[str] = DEFAULT_ALLOWED_LICENSES,
        require_redistribution_ok: bool = True,
        require_share_alike: Optional[bool] = False,
        allowed_privacy: Sequence[str] = ("public",),
        metadata_only: bool = False,
        include_blobs: bool = False,
        dry_run: bool = True,
        backend: Optional[HubBackend] = None,
        local_hub_root: Optional[str] = None,
    ) -> PublishResult:
        """Publish *snapshot_id*'s public slice to *hub_id*.

        Args:
            snapshot_id:               L4 snapshot to publish.
            hub_id:                    Target HF dataset repo (``org/name``).
            allowed_licenses:          SPDX allow-list; rows outside it
                                       cause the license gate to refuse.
            require_redistribution_ok: When True, every row must carry
                                       ``redistribution_ok=True``.
            require_share_alike:       Tri-state. ``True`` -> SA repo
                                       (every row must be SA). ``False``
                                       (the default) -> CC-BY umbrella
                                       (no SA contamination allowed).
                                       ``None`` -> mixing is permitted
                                       (only the VISCERAL metadata-only
                                       card uses this).
            allowed_privacy:           Privacy classes the publisher
                                       will honour.
            metadata_only:             When True, only L1 + dataset card
                                       reach the Hub.
            include_blobs:             When True, raw/converted/mask
                                       URIs are streamed through
                                       :class:`MinioObjectComponent`.
            dry_run:                   When True (the default), the
                                       license gate is enforced and
                                       artefacts are built in memory
                                       but never written.
            backend:                   Explicit :class:`HubBackend`. The
                                       Phase 3 integration tests pass a
                                       :class:`LocalFilesystemHub` here
                                       to stay offline.
            local_hub_root:            Convenience -- when ``backend`` is
                                       None, build a
                                       :class:`LocalFilesystemHub` at
                                       this root. Used by tests that
                                       only need the local mock.

        Returns:
            A :class:`PublishResult` summarising the artefacts the
            publisher produced. On a successful (non-dry-run) push, the
            snapshot's ``l4_cohort_snapshot.hf_publication_log`` is
            updated with the result.

        Raises:
            LicensePolicyError: when any row fails the publish-time
                license gate (per design invariant I5).
            CitationCompletenessError: when a DOI in ``l1_citations``
                fails to appear in the rendered README.
        """
        if backend is None:
            backend = LocalFilesystemHub(local_hub_root or "./.hf_mock_hub")
        publisher = HFPublisherComponent(
            self._require_catalog(),
            minio_component=self.minio_component,
        )
        policy = PublishPolicy(
            hub_id=hub_id,
            allowed_licenses=tuple(allowed_licenses),
            require_redistribution_ok=require_redistribution_ok,
            require_share_alike=require_share_alike,
            allowed_privacy=tuple(allowed_privacy),
            metadata_only=metadata_only,
            include_blobs=include_blobs,
        )
        return publisher.publish_snapshot(
            snapshot_id=snapshot_id,
            policy=policy,
            backend=backend,
            dry_run=dry_run,
        )
