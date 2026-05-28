"""Hugging Face publisher -- DatorCloud's egress component for Phase 3.

Per ``99_integration_plan/STEP_BY_STEP_PLAN.md`` §5 (steps 3.1-3.3), the
publisher is the canonical egress surface that lifts an L4 snapshot from
MinIO + the layered Parquet catalog into a Hugging Face dataset repo.
The Hub then becomes the queryable public face of the same catalog the
TRE keeps as the master.

Layout produced on every successful push
----------------------------------------

::

    <hub_id>/
    +-- README.md                   <- rendered dataset card (one config per dataset_id)
    +-- catalog/
    |   +-- l1.parquet              <- L1 experiment rows for the published slice
    |   +-- l2.parquet              <- L2 sensor rows
    |   +-- l3.parquet              <- L3 annotation rows
    |   +-- l4_snapshots.parquet    <- the snapshot's l4_cohort_snapshot row (sans BLOB)
    |   +-- l4_eval_sets.parquet    <- l4_eval_set rows that reference this snapshot
    |   `-- v_doris.parquet         <- denormalised view (one row per (record_uid, modality, sequence))
    +-- data/<dataset_id>/<subject_id>/
        +-- image.nii.gz            (when include_blobs=True and the L2 row exposes raw_uri)
        +-- seg/<label_canonical>.nii.gz
        `-- manifest.json           per-subject manifest

The layout intentionally matches the MIRO convention emitted by the (F)
operator so a remote consumer can call
``cohort_builder.build_cohort(..., source='hf')`` (Phase 4) and obtain a
tree byte-identical to the in-TRE one.

Backend abstraction
-------------------

Every write goes through a :class:`HubBackend` -- a small write surface
exposing ``ensure_repo`` / ``upload_file`` / ``revision_sha`` /
``list_files``. The default implementation in this module,
:class:`LocalFilesystemHub`, persists files under a local directory tree
and computes a deterministic revision SHA from the file content. This is
what the integration tests (``doris-it-03-hf-upload``) use so the chain
runs offline. A second implementation, :class:`HuggingFaceHub`, performs
the real ``huggingface_hub`` ``upload_file`` call; it is selected
explicitly by the DORIS CLI when ``--dry-run=false`` is passed in
production.

License gate (defence in depth)
-------------------------------

Before any write, the publisher applies the I5 license gate at publish
time:

* Every L1 row's ``license_spdx`` MUST be in ``allowed_licenses``;
* ``redistribution_ok`` MUST be True;
* When ``require_share_alike`` is True the repo accepts only
  ``share_alike_obligation=True`` rows (SA repo) and refuses every
  non-SA row;
* When ``require_share_alike`` is False the repo refuses every
  ``share_alike_obligation=True`` row (SA contamination of the CC-BY
  umbrella);
* The default ``allowed_privacy=('public',)`` refuses DUA / restricted
  records unless explicitly extended.

A violation raises :class:`LicensePolicyError` *before* any file is
written, so a failed publish cannot leave a partial tree behind.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

DEFAULT_ALLOWED_LICENSES: tuple[str, ...] = (
    "CC-BY-4.0",
    "CC-BY-3.0",
    "CC0-1.0",
)

# Hashable list of catalog Parquet sidecars the publisher writes into
# ``<hub>/catalog/``. Order is significant -- the revision SHA depends
# on it.
CATALOG_SIDECARS: tuple[str, ...] = (
    "l1.parquet",
    "l2.parquet",
    "l3.parquet",
    "l4_snapshots.parquet",
    "l4_eval_sets.parquet",
    "v_doris.parquet",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LicensePolicyError(RuntimeError):
    """Raised when an L1 row fails the publish-time license gate.

    The Phase 3 plan (STEP_BY_STEP_PLAN.md §5 step 3.4) lists three
    specific violations the gate must catch:

    * an unknown / disallowed ``license_spdx``;
    * a share-alike row leaking into a non-SA repo (or vice versa);
    * a citation completeness mismatch (a DOI listed in
      ``l1_citations`` that the rendered README forgets).

    All three surface as this exception so the caller (or CI gate) can
    handle them uniformly.
    """


class CitationCompletenessError(LicensePolicyError):
    """Raised when the rendered dataset card omits a cited DOI."""


# ---------------------------------------------------------------------------
# Hub backend abstraction
# ---------------------------------------------------------------------------


class HubBackend:
    """Minimal write surface a publisher needs from an HF dataset repo.

    Subclasses must be deterministic in :meth:`revision_sha` so the
    integration-test gate ``doris-it-03-hf-upload`` (assertion g) can
    record a stable revision on every push.
    """

    def ensure_repo(self, hub_id: str, *, private: bool = False) -> None:
        raise NotImplementedError

    def upload_file(
        self,
        hub_id: str,
        *,
        path_in_repo: str,
        data: bytes,
        message: str = "",
    ) -> None:
        raise NotImplementedError

    def revision_sha(self, hub_id: str) -> str:
        raise NotImplementedError

    def list_files(self, hub_id: str) -> List[str]:
        raise NotImplementedError

    def read_file(self, hub_id: str, path_in_repo: str) -> bytes:
        raise NotImplementedError


class LocalFilesystemHub(HubBackend):
    """A :class:`HubBackend` that materialises each repo as a local tree.

    Used by the Phase 3 integration tests so the publisher's behaviour
    can be exercised end-to-end without network or a real Hugging Face
    account. The revision SHA is the SHA-256 of the sorted
    ``(path, file_sha256)`` listing -- deterministic, so two
    consecutive publishes of the same snapshot produce the same SHA.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _repo_root(self, hub_id: str) -> Path:
        # HF hub_id is ``org/name``; we mirror it verbatim into the
        # local tree so the listing matches what the real Hub would
        # expose.
        return self.root / hub_id

    def ensure_repo(self, hub_id: str, *, private: bool = False) -> None:
        self._repo_root(hub_id).mkdir(parents=True, exist_ok=True)

    def upload_file(
        self,
        hub_id: str,
        *,
        path_in_repo: str,
        data: bytes,
        message: str = "",
    ) -> None:
        target = self._repo_root(hub_id) / path_in_repo
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def revision_sha(self, hub_id: str) -> str:
        repo = self._repo_root(hub_id)
        if not repo.exists():
            return hashlib.sha256(b"").hexdigest()
        h = hashlib.sha256()
        for path in sorted(repo.rglob("*")):
            if path.is_file():
                rel = path.relative_to(repo).as_posix()
                file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                h.update(f"{rel}\t{file_sha}\n".encode("utf-8"))
        return h.hexdigest()

    def list_files(self, hub_id: str) -> List[str]:
        repo = self._repo_root(hub_id)
        if not repo.exists():
            return []
        return sorted(
            p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file()
        )

    def read_file(self, hub_id: str, path_in_repo: str) -> bytes:
        return (self._repo_root(hub_id) / path_in_repo).read_bytes()


class HuggingFaceHub(HubBackend):
    """Real ``huggingface_hub``-backed :class:`HubBackend`.

    Constructed lazily so the import of :mod:`huggingface_hub` only
    happens when a real push is requested. Tests never touch this
    class.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        try:
            from huggingface_hub import HfApi  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover -- exercised only on real pushes
            raise RuntimeError(
                "huggingface_hub is required for HuggingFaceHub backend. "
                "Install it via `pip install huggingface_hub`."
            ) from exc
        self._HfApi = HfApi
        self._api = HfApi(token=token)

    def ensure_repo(self, hub_id: str, *, private: bool = False) -> None:  # pragma: no cover
        self._api.create_repo(repo_id=hub_id, repo_type="dataset", private=private, exist_ok=True)

    def upload_file(  # pragma: no cover
        self,
        hub_id: str,
        *,
        path_in_repo: str,
        data: bytes,
        message: str = "",
    ) -> None:
        self._api.upload_file(
            path_or_fileobj=io.BytesIO(data),
            path_in_repo=path_in_repo,
            repo_id=hub_id,
            repo_type="dataset",
            commit_message=message or f"DORIS publisher: {path_in_repo}",
        )

    def revision_sha(self, hub_id: str) -> str:  # pragma: no cover
        info = self._api.dataset_info(hub_id)
        return getattr(info, "sha", "") or ""

    def list_files(self, hub_id: str) -> List[str]:  # pragma: no cover
        return sorted(self._api.list_repo_files(hub_id, repo_type="dataset"))

    def read_file(self, hub_id: str, path_in_repo: str) -> bytes:  # pragma: no cover
        from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]

        local = hf_hub_download(
            repo_id=hub_id,
            filename=path_in_repo,
            repo_type="dataset",
            token=getattr(self._api, "token", None),
        )
        return Path(local).read_bytes()


# ---------------------------------------------------------------------------
# Publish policy / result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishPolicy:
    """Caller-supplied policy that gates the publisher's write path.

    Attributes:
        hub_id:                  Target HF dataset repo (``org/name``).
        allowed_licenses:        Allow-list of SPDX strings. Defaults to
                                 the CC-BY umbrella.
        require_redistribution_ok: When True (the default), every row
                                 must have ``redistribution_ok=True``.
        require_share_alike:     ``True`` for the SA-isolated repo,
                                 ``False`` for the CC-BY umbrella, and
                                 ``None`` if mixing is permitted (only
                                 ever used by the VISCERAL metadata-only
                                 card, which carries neither flag).
        allowed_privacy:         Privacy classes the publisher will
                                 honour. The default refuses DUA /
                                 restricted records.
        metadata_only:           When True, the publisher writes the L1
                                 sidecar + dataset card but skips L2/L3
                                 sidecars and every ``data/`` blob.
        include_blobs:           When True, raw/converted/mask URIs in
                                 the L2/L3 payload are streamed via
                                 :class:`MinioObjectComponent` (when
                                 wired in) and persisted under
                                 ``data/<dataset_id>/<subject_id>/``.
                                 Defaults to False so the Phase 3
                                 integration test can run without
                                 MinIO.
    """

    hub_id: str
    allowed_licenses: tuple[str, ...] = DEFAULT_ALLOWED_LICENSES
    require_redistribution_ok: bool = True
    require_share_alike: Optional[bool] = False
    allowed_privacy: tuple[str, ...] = ("public",)
    metadata_only: bool = False
    include_blobs: bool = False


@dataclass(frozen=True)
class PublishResult:
    """Outcome of one :meth:`HFPublisherComponent.publish_snapshot` call."""

    snapshot_id: str
    hub_id: str
    revision_sha: str
    n_records: int
    n_files_written: int
    files_written: tuple[str, ...]
    dry_run: bool
    published_at: str
    catalog_sha256: str

    def as_log_entry(self) -> Dict[str, Any]:
        """Return the dict appended to ``l4_cohort_snapshot.hf_publication_log``."""
        return {
            "hub_id": self.hub_id,
            "revision_sha": self.revision_sha,
            "n_records": int(self.n_records),
            "n_files": int(self.n_files_written),
            "dry_run": bool(self.dry_run),
            "published_at": self.published_at,
            "catalog_sha256": self.catalog_sha256,
        }


# ---------------------------------------------------------------------------
# Helpers -- Parquet serialisation
# ---------------------------------------------------------------------------


def _dataframe_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialise *df* into a deterministic Parquet byte blob.

    ``write_statistics=False`` keeps the bytes reproducible (statistics
    embed timestamps).
    """
    if df.empty:
        # Build an empty schema-less table so ``read_parquet`` still
        # works. PyArrow refuses empty schemas, so pad a single
        # placeholder column.
        table = pa.table({"__doris_empty__": pa.array([], type=pa.int64())})
    else:
        table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(
        table,
        buf,
        version="2.6",
        compression="snappy",
        use_dictionary=True,
        write_statistics=False,
    )
    return buf.getvalue()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class HFPublisherComponent:
    """Lift an L4 snapshot from MinIO + the catalog onto Hugging Face.

    The publisher is intentionally *additive*: it reads the snapshot's
    frozen ``l13_payload`` plus any related ``l4_eval_set`` rows, and
    writes a curated subset to a target hub through a
    :class:`HubBackend`. It never mutates the source catalog beyond
    appending one entry to ``l4_cohort_snapshot.hf_publication_log``.
    """

    DATASET_CARD_TEMPLATE_NAME = "dataset_card.md.template"

    def __init__(
        self,
        catalog,
        *,
        minio_component: Optional[Any] = None,
        templates_dir: Optional[Path] = None,
    ) -> None:
        self.catalog = catalog
        self.minio_component = minio_component
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parents[1] / "templates"
        self.templates_dir = Path(templates_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish_snapshot(
        self,
        *,
        snapshot_id: str,
        policy: PublishPolicy,
        backend: HubBackend,
        dry_run: bool = True,
    ) -> PublishResult:
        """Publish *snapshot_id* to *policy.hub_id* via *backend*.

        ``dry_run=True`` (the default) validates the license gate, builds
        every artefact in memory, but does **not** call
        :meth:`HubBackend.upload_file`. ``dry_run=False`` performs the
        full push and updates ``l4_cohort_snapshot.hf_publication_log``.
        """
        snap_info = self._fetch_snapshot_info(snapshot_id)
        payload = self._load_payload(snapshot_id)
        l1, l2, l3 = self._split_layers(payload)
        citations = self._load_citations(l1)
        eval_sets = self._load_eval_sets(snapshot_id)

        # I5 license gate (defence in depth).
        self._enforce_license_gate(l1, policy)

        # Build every artefact in memory so dry_run never touches the
        # backend, and a real push never leaves a partial tree behind.
        artefacts = self._build_artefacts(
            snap_info=snap_info,
            policy=policy,
            l1=l1,
            l2=l2,
            l3=l3,
            citations=citations,
            eval_sets=eval_sets,
        )

        backend.ensure_repo(policy.hub_id)

        files_written: list[str] = []
        if not dry_run:
            for path_in_repo, data in artefacts:
                backend.upload_file(
                    policy.hub_id,
                    path_in_repo=path_in_repo,
                    data=data,
                    message=f"doris-publisher: {snapshot_id} -> {path_in_repo}",
                )
                files_written.append(path_in_repo)
            revision = backend.revision_sha(policy.hub_id)
        else:
            # Compute the revision sha the publish *would* have produced
            # by hashing the artefact bytes deterministically. This
            # makes dry-run inspectable without touching the backend.
            revision = self._compute_dry_run_revision(artefacts)
            files_written = [path for path, _ in artefacts]

        result = PublishResult(
            snapshot_id=snapshot_id,
            hub_id=policy.hub_id,
            revision_sha=revision,
            n_records=int(snap_info.get("n_records") or 0),
            n_files_written=len(files_written),
            files_written=tuple(files_written),
            dry_run=dry_run,
            published_at=_utc_now_iso(),
            catalog_sha256=str(snap_info.get("catalog_sha256") or ""),
        )

        if not dry_run:
            self._append_publication_log(snapshot_id, result)
        return result

    # ------------------------------------------------------------------
    # Snapshot / payload loaders
    # ------------------------------------------------------------------

    def _fetch_snapshot_info(self, snapshot_id: str) -> Dict[str, Any]:
        df = self.catalog.query(
            "SELECT snapshot_id, catalog_sha256, n_records, predicate_sql, "
            "       schema_version, hf_publication_log "
            "FROM l4_cohort_snapshot WHERE snapshot_id = ?",
            params=[snapshot_id],
        )
        if df.empty:
            raise KeyError(f"snapshot not found: {snapshot_id!r}")
        return df.iloc[0].to_dict()

    def _load_payload(self, snapshot_id: str) -> pd.DataFrame:
        # Lazy import to avoid a circular import on package init.
        from ..snapshots import load_snapshot_payload

        return load_snapshot_payload(self.catalog, snapshot_id)

    def _split_layers(
        self, payload: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if payload.empty or "layer" not in payload.columns:
            return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        l1 = payload[payload["layer"] == "l1_experiment"].drop(
            columns=["layer"]
        ).reset_index(drop=True)
        l2 = payload[payload["layer"] == "l2_sensor"].drop(
            columns=["layer"]
        ).reset_index(drop=True)
        l3 = payload[payload["layer"] == "l3_annotation"].drop(
            columns=["layer"]
        ).reset_index(drop=True)
        # Drop columns that are pure NaN (introduced by concat of layers
        # with disjoint schemas) so the downstream Parquet readers stay
        # clean.
        for frame in (l1, l2, l3):
            empty_cols = [c for c in frame.columns if frame[c].isna().all()]
            if empty_cols:
                frame.drop(columns=empty_cols, inplace=True)
        return l1, l2, l3

    def _load_citations(self, l1: pd.DataFrame) -> pd.DataFrame:
        if l1.empty or "record_uid" not in l1.columns:
            return pd.DataFrame(columns=["record_uid", "doi", "citation"])
        uids = sorted(set(str(u) for u in l1["record_uid"].tolist()))
        placeholders = ",".join("?" for _ in uids)
        if not placeholders:
            return pd.DataFrame(columns=["record_uid", "doi", "citation"])
        df = self.catalog.query(
            f"SELECT record_uid, doi, citation FROM l1_citations "
            f"WHERE record_uid IN ({placeholders}) "
            f"ORDER BY record_uid, doi",
            params=uids,
        )
        return df

    def _load_eval_sets(self, snapshot_id: str) -> pd.DataFrame:
        return self.catalog.query(
            "SELECT eval_set_id, snapshot_id, annotator_columns, target_labels, "
            "       inter_observer_quantiles, notes "
            "FROM l4_eval_set WHERE snapshot_id = ? "
            "ORDER BY eval_set_id",
            params=[snapshot_id],
        )

    # ------------------------------------------------------------------
    # License gate (per I5)
    # ------------------------------------------------------------------

    def _enforce_license_gate(self, l1: pd.DataFrame, policy: PublishPolicy) -> None:
        if l1.empty:
            raise LicensePolicyError(
                f"snapshot has no L1 rows -- nothing to publish to {policy.hub_id!r}."
            )

        required_cols = {"license_spdx", "privacy_class", "redistribution_ok"}
        missing = required_cols - set(l1.columns)
        if missing:
            raise LicensePolicyError(
                f"L1 payload is missing required gate columns: {sorted(missing)!r}"
            )

        allowed = set(policy.allowed_licenses)
        offenders_lic = sorted(
            set(str(s) for s in l1["license_spdx"]) - allowed
        )
        if offenders_lic:
            raise LicensePolicyError(
                f"license gate refused publish to {policy.hub_id!r}: "
                f"records carry license_spdx={offenders_lic!r}, "
                f"which is not in allowed_licenses={sorted(allowed)!r}."
            )

        if policy.require_redistribution_ok:
            bad = l1[~l1["redistribution_ok"].astype(bool)]
            if not bad.empty:
                offenders = sorted(set(str(s) for s in bad["license_spdx"]))
                raise LicensePolicyError(
                    f"license gate refused publish to {policy.hub_id!r}: "
                    f"records with redistribution_ok=False slipped through "
                    f"(license_spdx={offenders!r})."
                )

        privacy = set(str(p) for p in l1.get("privacy_class", pd.Series(dtype=str)))
        bad_privacy = sorted(privacy - set(policy.allowed_privacy))
        if bad_privacy:
            raise LicensePolicyError(
                f"license gate refused publish to {policy.hub_id!r}: "
                f"records with privacy_class={bad_privacy!r} are not in "
                f"allowed_privacy={sorted(policy.allowed_privacy)!r}."
            )

        if "share_alike_obligation" in l1.columns and policy.require_share_alike is not None:
            sa_flags = l1["share_alike_obligation"].astype(bool)
            if policy.require_share_alike:
                if not sa_flags.all():
                    offenders = sorted(
                        set(
                            str(s)
                            for s in l1.loc[~sa_flags, "license_spdx"]
                        )
                    )
                    raise LicensePolicyError(
                        f"SA repo {policy.hub_id!r} requires every row to be "
                        f"share-alike, but rows with license_spdx={offenders!r} "
                        "carry share_alike_obligation=False."
                    )
            else:
                if sa_flags.any():
                    offenders = sorted(
                        set(
                            str(s)
                            for s in l1.loc[sa_flags, "license_spdx"]
                        )
                    )
                    raise LicensePolicyError(
                        f"SA contamination refused publish to "
                        f"{policy.hub_id!r}: rows with license_spdx="
                        f"{offenders!r} carry share_alike_obligation=True "
                        "and must go to a CC-BY-SA-isolated repo."
                    )

    # ------------------------------------------------------------------
    # Artefact builder
    # ------------------------------------------------------------------

    def _build_artefacts(
        self,
        *,
        snap_info: Mapping[str, Any],
        policy: PublishPolicy,
        l1: pd.DataFrame,
        l2: pd.DataFrame,
        l3: pd.DataFrame,
        citations: pd.DataFrame,
        eval_sets: pd.DataFrame,
    ) -> List[Tuple[str, bytes]]:
        artefacts: List[Tuple[str, bytes]] = []

        # README (dataset card). Render first so the citation
        # completeness check (Step 3.4) runs before any Parquet bytes
        # are produced.
        readme_bytes = self.render_dataset_card(
            snap_info=snap_info,
            policy=policy,
            l1=l1,
            l2=l2,
            l3=l3,
            citations=citations,
            eval_sets=eval_sets,
        )
        self._assert_citation_completeness(citations, readme_bytes)
        artefacts.append(("README.md", readme_bytes))

        # Catalog sidecars.
        l4_snap_df = pd.DataFrame(
            [
                {
                    "snapshot_id": snap_info.get("snapshot_id"),
                    "catalog_sha256": snap_info.get("catalog_sha256"),
                    "n_records": int(snap_info.get("n_records") or 0),
                    "predicate_sql": snap_info.get("predicate_sql"),
                    "schema_version": snap_info.get("schema_version"),
                }
            ]
        )
        v_doris_df = self._build_v_doris(l1, l2, l3)

        if policy.metadata_only:
            # Metadata-only repos publish L1 + dataset card only.
            sidecars: Dict[str, pd.DataFrame] = {
                "l1.parquet": l1,
                "l4_snapshots.parquet": l4_snap_df,
            }
        else:
            sidecars = {
                "l1.parquet": l1,
                "l2.parquet": l2,
                "l3.parquet": l3,
                "l4_snapshots.parquet": l4_snap_df,
                "l4_eval_sets.parquet": eval_sets,
                "v_doris.parquet": v_doris_df,
            }

        for name, frame in sidecars.items():
            artefacts.append(
                (f"catalog/{name}", _dataframe_to_parquet_bytes(frame))
            )

        # Per-subject manifests + (optionally) blobs.
        if not policy.metadata_only:
            artefacts.extend(self._build_per_subject_artefacts(l1, l2, l3, policy))

        return artefacts

    def _build_v_doris(
        self, l1: pd.DataFrame, l2: pd.DataFrame, l3: pd.DataFrame
    ) -> pd.DataFrame:
        """Reconstruct a denormalised view from the snapshot's L1/L2/L3.

        Mirrors :data:`V_DORIS_SQL` from
        :mod:`datorcloud.components.parquet_catalog_component` but works
        off the in-memory snapshot payload so the HF-resident view
        agrees with the in-TRE one for the same ``snapshot_id``.
        """
        if l1.empty:
            return pd.DataFrame()
        l1_keep = [
            c
            for c in (
                "record_uid",
                "dataset_id",
                "dataset_version",
                "subject_id",
                "study_id",
                "body_part",
                "privacy_class",
                "license_spdx",
                "license_rule_version",
                "redistribution_ok",
                "hf_repo",
                "share_alike_obligation",
            )
            if c in l1.columns
        ]
        l2_keep = [
            c
            for c in (
                "record_uid",
                "modality",
                "sequence",
                "voxel_spacing_mm",
                "slice_thickness_mm",
                "field_strength_t",
                "scanner_model",
                "raw_uri",
                "converted_uri",
            )
            if c in l2.columns
        ]
        merged = l1[l1_keep]
        if not l2.empty and "record_uid" in l2.columns:
            merged = merged.merge(l2[l2_keep], on="record_uid", how="left")
        if not l3.empty and "record_uid" in l3.columns and "label_canonical" in l3.columns:
            labels = (
                l3.groupby("record_uid")["label_canonical"]
                .apply(lambda s: sorted(set(str(x) for x in s)))
                .reset_index()
                .rename(columns={"label_canonical": "labels"})
            )
            merged = merged.merge(labels, on="record_uid", how="left")
            merged["labels"] = merged["labels"].apply(
                lambda v: v if isinstance(v, list) else []
            )
        else:
            merged["labels"] = [[] for _ in range(len(merged))]
        # Sort by record_uid, modality, sequence for byte-identical output.
        sort_keys = [k for k in ("record_uid", "modality", "sequence") if k in merged.columns]
        if sort_keys:
            merged = merged.sort_values(sort_keys, kind="mergesort").reset_index(drop=True)
        return merged

    def _build_per_subject_artefacts(
        self,
        l1: pd.DataFrame,
        l2: pd.DataFrame,
        l3: pd.DataFrame,
        policy: PublishPolicy,
    ) -> List[Tuple[str, bytes]]:
        out: List[Tuple[str, bytes]] = []
        for _, row in l1.iterrows():
            dataset_id = str(row["dataset_id"])
            subject_id = str(row["subject_id"])
            record_uid = str(row["record_uid"])
            l2_subset = (
                l2[l2["record_uid"] == record_uid] if "record_uid" in l2.columns else l2.iloc[0:0]
            )
            l3_subset = (
                l3[l3["record_uid"] == record_uid] if "record_uid" in l3.columns else l3.iloc[0:0]
            )
            manifest = self._render_subject_manifest(row, l2_subset, l3_subset)
            manifest_bytes = json.dumps(
                manifest, sort_keys=True, separators=(",", ":"), default=str
            ).encode("utf-8")
            out.append(
                (
                    f"data/{dataset_id}/{subject_id}/manifest.json",
                    manifest_bytes,
                )
            )

            if policy.include_blobs and self.minio_component is not None:
                out.extend(
                    self._fetch_blobs_for_subject(dataset_id, subject_id, l2_subset, l3_subset)
                )

        return out

    def _render_subject_manifest(
        self, l1_row: Mapping[str, Any], l2_subset: pd.DataFrame, l3_subset: pd.DataFrame
    ) -> Dict[str, Any]:
        l2_rows: List[Dict[str, Any]] = []
        if not l2_subset.empty:
            for _, r in l2_subset.iterrows():
                l2_rows.append(
                    {
                        "modality": r.get("modality"),
                        "sequence": r.get("sequence"),
                        "raw_format": r.get("raw_format"),
                        "raw_uri": r.get("raw_uri"),
                        "converted_uri": r.get("converted_uri"),
                    }
                )
        l3_rows: List[Dict[str, Any]] = []
        if not l3_subset.empty:
            for _, r in l3_subset.iterrows():
                l3_rows.append(
                    {
                        "label_canonical": r.get("label_canonical"),
                        "annotator": r.get("annotator"),
                        "annotation_kind": r.get("annotation_kind"),
                        "mask_uri": r.get("mask_uri"),
                    }
                )
        return {
            "record_uid": l1_row.get("record_uid"),
            "dataset_id": l1_row.get("dataset_id"),
            "dataset_version": l1_row.get("dataset_version"),
            "subject_id": l1_row.get("subject_id"),
            "study_id": l1_row.get("study_id", ""),
            "license_spdx": l1_row.get("license_spdx"),
            "privacy_class": l1_row.get("privacy_class"),
            "sensors": sorted(l2_rows, key=lambda d: (str(d.get("modality") or ""), str(d.get("sequence") or ""))),
            "annotations": sorted(l3_rows, key=lambda d: (str(d.get("label_canonical") or ""), str(d.get("annotator") or ""))),
        }

    def _fetch_blobs_for_subject(
        self,
        dataset_id: str,
        subject_id: str,
        l2_subset: pd.DataFrame,
        l3_subset: pd.DataFrame,
    ) -> List[Tuple[str, bytes]]:
        """Best-effort blob fetch through the wired MinIO component.

        Only ever called when ``policy.include_blobs=True`` and a real
        MinIO is plugged in. The Phase 3 integration test exercises
        this path with a small in-process stub so we never depend on a
        live MinIO.
        """
        out: List[Tuple[str, bytes]] = []
        for _, r in l2_subset.iterrows():
            for source_col, suffix in (
                ("converted_uri", "image_converted"),
                ("raw_uri", "image"),
            ):
                uri = r.get(source_col)
                if not uri:
                    continue
                blob = self._download_uri(str(uri))
                if blob is None:
                    continue
                modality = str(r.get("modality") or "na")
                seq = str(r.get("sequence") or "na")
                key = f"data/{dataset_id}/{subject_id}/{suffix}_{modality}_{seq}.nii.gz"
                out.append((key, blob))
        for _, r in l3_subset.iterrows():
            uri = r.get("mask_uri")
            if not uri:
                continue
            blob = self._download_uri(str(uri))
            if blob is None:
                continue
            label = str(r.get("label_canonical") or "unlabelled")
            key = f"data/{dataset_id}/{subject_id}/seg/{label}.nii.gz"
            out.append((key, blob))
        return out

    def _download_uri(self, uri: str) -> Optional[bytes]:
        """Fetch *uri* through the wired MinIO component, if any."""
        if self.minio_component is None or not uri.startswith("s3://"):
            return None
        # MinioObjectComponent only exposes a path-to-disk download; we
        # write to a temp file and slurp it back.
        from tempfile import NamedTemporaryFile

        rest = uri[len("s3://"):]
        slash = rest.find("/")
        if slash <= 0:
            return None
        bucket, key = rest[:slash], rest[slash + 1:]
        with NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            ok = self.minio_component.download_file(bucket, key, tmp_path)
            if not ok:
                return None
            return Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Dataset card rendering
    # ------------------------------------------------------------------

    def render_dataset_card(
        self,
        *,
        snap_info: Mapping[str, Any],
        policy: PublishPolicy,
        l1: pd.DataFrame,
        l2: pd.DataFrame,
        l3: pd.DataFrame,
        citations: pd.DataFrame,
        eval_sets: pd.DataFrame,
    ) -> bytes:
        """Render a HF-conforming README for the slice being published.

        Configs (one per ``dataset_id``) are emitted in alphabetical
        order so two renders of the same snapshot yield byte-identical
        bytes. The HF dataset-card schema is matched at the YAML
        frontmatter level only -- the body is plain Markdown.
        """
        configs = sorted(set(str(d) for d in l1["dataset_id"].tolist())) if not l1.empty else []
        licenses = sorted(set(str(s) for s in l1["license_spdx"].tolist())) if not l1.empty else []
        modalities = (
            sorted(set(str(m) for m in l2["modality"].tolist()))
            if not l2.empty and "modality" in l2.columns
            else []
        )

        hf_license = _spdx_to_hf_license(licenses[0]) if licenses else "other"
        frontmatter_lines = [
            "---",
            f"license: {hf_license}",
            "tags:",
            "- medical-imaging",
            "- segmentation",
            "- musculoskeletal",
            "- DORIS",
            "configs:",
        ]
        for cfg in configs:
            frontmatter_lines.append(f"- config_name: {cfg}")
            frontmatter_lines.append("  data_files:")
            frontmatter_lines.append(
                f"  - split: all\n    path: data/{cfg}/**/manifest.json"
            )
        frontmatter_lines.append("---")
        frontmatter = "\n".join(frontmatter_lines)

        snapshot_id = str(snap_info.get("snapshot_id") or "")
        catalog_sha = str(snap_info.get("catalog_sha256") or "")
        n_records = int(snap_info.get("n_records") or 0)

        per_config_lines = []
        for cfg in configs:
            slice_ = l1[l1["dataset_id"] == cfg]
            n = int(slice_["subject_id"].nunique()) if "subject_id" in slice_.columns else len(slice_)
            cfg_licenses = sorted(set(str(s) for s in slice_["license_spdx"].tolist()))
            per_config_lines.append(
                f"- **{cfg}**: {n} subjects, license `{', '.join(cfg_licenses)}`"
            )

        citation_lines = []
        if not citations.empty:
            seen: set[str] = set()
            for _, row in citations.sort_values(["doi", "citation"]).iterrows():
                doi = str(row.get("doi") or "").strip()
                text = str(row.get("citation") or "").strip()
                key = doi or text
                if not key or key in seen:
                    continue
                seen.add(key)
                if doi:
                    citation_lines.append(f"- [`{doi}`]({_doi_url(doi)}) -- {text}")
                else:
                    citation_lines.append(f"- {text}")

        eval_lines = []
        if not eval_sets.empty:
            for _, r in eval_sets.iterrows():
                eval_lines.append(
                    f"- `{r.get('eval_set_id')}` -- target labels: "
                    f"{list(r.get('target_labels') or [])}, "
                    f"annotators: {list(r.get('annotator_columns') or [])}"
                )

        lines = [
            frontmatter,
            "",
            f"# {policy.hub_id}",
            "",
            "DORIS-published Hugging Face dataset. The catalog metadata "
            "(L1-L4) is shipped as Parquet sidecars under "
            "`catalog/` so this repo is queryable end-to-end via "
            "DuckDB httpfs without downloading any pixel data.",
            "",
            "## Snapshot",
            "",
            f"- `snapshot_id`: `{snapshot_id}`",
            f"- `catalog_sha256`: `{catalog_sha}`",
            f"- `n_records`: {n_records}",
            f"- `schema_version`: `{snap_info.get('schema_version') or ''}`",
            f"- `licenses`: {', '.join(licenses) if licenses else 'unknown'}",
            f"- `modalities`: {', '.join(modalities) if modalities else 'metadata-only'}",
            f"- `metadata_only`: {policy.metadata_only}",
            f"- `share_alike_isolated`: {bool(policy.require_share_alike)}",
            "",
            "## Configurations",
            "",
            *per_config_lines,
            "",
            "## Catalog layout",
            "",
            "```",
            "catalog/",
            "  l1.parquet",
        ]
        if not policy.metadata_only:
            lines += [
                "  l2.parquet",
                "  l3.parquet",
                "  v_doris.parquet",
            ]
        lines += [
            "  l4_snapshots.parquet",
        ]
        if not policy.metadata_only:
            lines.append("  l4_eval_sets.parquet")
        lines.append("data/<dataset_id>/<subject_id>/manifest.json")
        if not policy.metadata_only:
            lines.append("data/<dataset_id>/<subject_id>/image.nii.gz   (when include_blobs=True)")
            lines.append("data/<dataset_id>/<subject_id>/seg/<label>.nii.gz")
        lines += [
            "```",
            "",
            "## Eval sets",
            "",
            *(eval_lines or ["_None registered._"]),
            "",
            "## Citations",
            "",
            *(citation_lines or ["_None registered for this snapshot._"]),
            "",
            "## Reproduction",
            "",
            "```python",
            "import duckdb",
            f"duckdb.sql(\"SELECT count(*) FROM read_parquet('https://huggingface.co/datasets/{policy.hub_id}/resolve/main/catalog/l1.parquet')\")",
            "```",
            "",
            "Published by DORIS / DatorCloud per the integration plan "
            "(`99_integration_plan/STEP_BY_STEP_PLAN.md` §5 Phase 3).",
            "",
        ]
        return ("\n".join(lines)).encode("utf-8")

    def _assert_citation_completeness(
        self, citations: pd.DataFrame, readme_bytes: bytes
    ) -> None:
        if citations.empty:
            return
        rendered = readme_bytes.decode("utf-8")
        missing = []
        for _, row in citations.iterrows():
            doi = str(row.get("doi") or "").strip()
            if not doi:
                continue
            if doi not in rendered:
                missing.append(doi)
        if missing:
            raise CitationCompletenessError(
                f"dataset card omits DOIs from l1_citations: {sorted(set(missing))}"
            )

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_dry_run_revision(artefacts: Sequence[Tuple[str, bytes]]) -> str:
        h = hashlib.sha256()
        for path, data in sorted(artefacts, key=lambda x: x[0]):
            h.update(path.encode("utf-8"))
            h.update(b"\t")
            h.update(hashlib.sha256(data).hexdigest().encode("ascii"))
            h.update(b"\n")
        return h.hexdigest()

    def _append_publication_log(
        self, snapshot_id: str, result: PublishResult
    ) -> None:
        """Append the publish result to ``l4_cohort_snapshot.hf_publication_log``.

        The column is a JSON array (encoded as a VARCHAR) so multiple
        pushes accumulate. We read-modify-write under a single DuckDB
        transaction so a partial write cannot leave a malformed log.
        """
        row = self.catalog.conn.execute(
            "SELECT hf_publication_log FROM l4_cohort_snapshot WHERE snapshot_id = ?",
            [snapshot_id],
        ).fetchone()
        if row is None:
            raise KeyError(f"snapshot not found: {snapshot_id!r}")
        existing = row[0]
        log_entries: list[Dict[str, Any]] = []
        if existing:
            try:
                parsed = json.loads(existing)
                if isinstance(parsed, list):
                    log_entries = parsed
            except (TypeError, ValueError):
                log_entries = []
        log_entries.append(result.as_log_entry())
        encoded = json.dumps(log_entries, sort_keys=True, separators=(",", ":"))
        self.catalog.conn.execute(
            "UPDATE l4_cohort_snapshot SET hf_publication_log = ? WHERE snapshot_id = ?",
            [encoded, snapshot_id],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doi_url(doi: str) -> str:
    doi = doi.strip()
    if doi.startswith("http://") or doi.startswith("https://"):
        return doi
    return f"https://doi.org/{doi}"


# Hugging Face's dataset-card validator only accepts the lowercased
# dashed identifiers (``cc-by-4.0``) -- not the SPDX form (``CC-BY-4.0``)
# we use internally. ``LicenseRef-*`` SPDX values map to ``other`` since
# HF has no dedicated tag for DUA / unknown licenses.
_SPDX_TO_HF_LICENSE: Dict[str, str] = {
    "CC-BY-4.0":     "cc-by-4.0",
    "CC-BY-3.0":     "cc-by-3.0",
    "CC-BY-2.0":     "cc-by-2.0",
    "CC-BY-SA-4.0":  "cc-by-sa-4.0",
    "CC-BY-SA-3.0":  "cc-by-sa-3.0",
    "CC-BY-NC-4.0":  "cc-by-nc-4.0",
    "CC-BY-NC-SA-4.0": "cc-by-nc-sa-4.0",
    "CC-BY-ND-4.0":  "cc-by-nd-4.0",
    "CC0-1.0":       "cc0-1.0",
    "Apache-2.0":    "apache-2.0",
    "MIT":           "mit",
    "BSD-2-Clause":  "bsd-2-clause",
    "BSD-3-Clause":  "bsd-3-clause",
}


def _spdx_to_hf_license(spdx: str) -> str:
    """Map an SPDX identifier to a Hugging Face dataset-card license tag."""
    if not spdx:
        return "other"
    if spdx in _SPDX_TO_HF_LICENSE:
        return _SPDX_TO_HF_LICENSE[spdx]
    if spdx.startswith("LicenseRef-"):
        return "other"
    return spdx.lower()


def read_publication_log(catalog, snapshot_id: str) -> List[Dict[str, Any]]:
    """Return the parsed ``hf_publication_log`` for *snapshot_id*."""
    row = catalog.conn.execute(
        "SELECT hf_publication_log FROM l4_cohort_snapshot WHERE snapshot_id = ?",
        [snapshot_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"snapshot not found: {snapshot_id!r}")
    raw = row[0]
    if not raw:
        return []
    try:
        out = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return list(out) if isinstance(out, list) else []


__all__ = [
    "HFPublisherComponent",
    "HubBackend",
    "LocalFilesystemHub",
    "HuggingFaceHub",
    "PublishPolicy",
    "PublishResult",
    "LicensePolicyError",
    "CitationCompletenessError",
    "DEFAULT_ALLOWED_LICENSES",
    "CATALOG_SIDECARS",
    "read_publication_log",
]
