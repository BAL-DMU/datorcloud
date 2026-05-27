"""Command-line entry point for DatorCloud.

The CLI is intentionally small: it exposes the four pipeline stages that the
orchestrator implements, plus a ``version`` command. Each subcommand maps 1:1 to
a method on :class:`DatorCloudOrchestrator` so users get the exact same behavior
as the Python and Dagster surfaces.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv()
except ImportError:  # python-dotenv is optional; bare os.environ still works.
    pass

from . import __version__
from .core import DatorCloudOrchestrator

log = logging.getLogger("datorcloud.cli")


def _env_path(name: str, default: str) -> str:
    """Return the env-var ``name`` or ``default`` if unset/empty."""
    value = os.environ.get(name)
    return value if value else default


def _env_endpoint() -> str:
    """Return ``S3_ENDPOINT`` stripped of any scheme prefix."""
    raw = os.environ.get("S3_ENDPOINT", "minio:9090")
    return raw.replace("http://", "").replace("https://", "")


def _parse_kv_pairs(values: Optional[Sequence[str]]) -> Dict[str, str]:
    """Turn ``["a=b", "c=d"]`` into ``{"a": "b", "c": "d"}``."""
    out: Dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"Expected NAME=PATH style argument, got: {item!r}"
            )
        name, _, path = item.partition("=")
        out[name.strip()] = path.strip()
    return out


def _parse_filters(values: Optional[Sequence[str]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"Expected COLUMN=VALUE filter, got: {item!r}"
            )
        col, _, value = item.partition("=")
        out[col.strip()] = value.strip()
    return out


def _build_orchestrator(
    args: argparse.Namespace, *, require_minio: bool = True
) -> DatorCloudOrchestrator:
    """Construct the orchestrator from CLI args.

    CLI defaults pull from the environment (which has been populated by
    ``load_dotenv()`` above) without hard-coding any credentials. Missing
    credentials surface as a clear ``ValueError`` from the underlying
    components.

    The catalog-only verbs (``query --sql``, ``snapshot``, etc.) pass
    ``require_minio=False`` so callers can drive the L1-L4 catalog
    against a local DuckDB / Parquet root without configuring MinIO.
    """
    if require_minio and (not args.minio_access_key or not args.minio_secret_key):
        raise SystemExit(
            "MinIO credentials are missing. Set S3_ACCESS_KEY and S3_SECRET_KEY "
            "in your .env file, or pass --minio-access-key / --minio-secret-key."
        )
    kwargs: Dict[str, Any] = dict(
        minio_endpoint=args.minio_endpoint,
        minio_access_key=args.minio_access_key,
        minio_secret_key=args.minio_secret_key,
        minio_secure=args.minio_secure,
        data_bucket=args.data_bucket,
        metadata_bucket=args.metadata_bucket,
        local_download_dir=args.local_download_dir,
        duckdb_extension_path=args.duckdb_extension_path,
        catalog_base_uri=getattr(args, "catalog_base_uri", None)
        or os.environ.get("DATORCLOUD_CATALOG_URI"),
    )
    if not require_minio and (
        not args.minio_access_key or not args.minio_secret_key
    ):
        # Catalog-only mode: stub out credentials so the minio component
        # is constructed but never used.
        kwargs["minio_access_key"] = args.minio_access_key or "_catalog_only_"
        kwargs["minio_secret_key"] = args.minio_secret_key or "_catalog_only_"
    return DatorCloudOrchestrator(**kwargs)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--minio-endpoint",
        default=_env_endpoint(),
        help="MinIO host:port. Defaults to $S3_ENDPOINT (no scheme).",
    )
    parser.add_argument(
        "--minio-access-key",
        default=os.environ.get("S3_ACCESS_KEY"),
        help="MinIO access key. Defaults to $S3_ACCESS_KEY (required).",
    )
    parser.add_argument(
        "--minio-secret-key",
        default=os.environ.get("S3_SECRET_KEY"),
        help="MinIO secret key. Defaults to $S3_SECRET_KEY (required).",
    )
    parser.add_argument("--minio-secure", action="store_true")
    parser.add_argument(
        "--data-bucket",
        default=os.environ.get("DATA_BUCKET", "orx-datalake"),
    )
    parser.add_argument(
        "--metadata-bucket",
        default=os.environ.get("METADATA_BUCKET", "orx-metadata"),
    )
    parser.add_argument(
        "--local-download-dir",
        default=_env_path("RETRIEVED_DATA_PATH", "./retrieved_data"),
    )
    parser.add_argument(
        "--duckdb-extension-path",
        default=os.environ.get("DUCKDB_HTTPFS_EXTENSION_PATH"),
    )
    parser.add_argument(
        "--catalog-base-uri",
        dest="catalog_base_uri",
        default=os.environ.get("DATORCLOUD_CATALOG_URI"),
        help=(
            "Root URI for the L1-L4 Parquet catalog "
            "(file:// or s3:// or bare path). "
            "Defaults to $DATORCLOUD_CATALOG_URI."
        ),
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase log verbosity."
    )


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _cmd_upload(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    paths = _parse_kv_pairs(args.dataset)
    results = orchestrator.upload_datasets(paths)
    print(json.dumps({k: len(v) for k, v in results.items()}, indent=2))
    return 0


def _cmd_metadata(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    paths = _parse_kv_pairs(args.dataset)
    df = orchestrator.generate_and_upload_metadata(
        dataset_dirs=paths,
        output_file=args.output_file,
        object_name=args.object_name,
    )
    print(json.dumps({"records": len(df), "output_file": args.output_file}, indent=2))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    # New Phase-1 path: --sql goes directly through the formal (Q)
    # operator on the L1-L4 catalog. The legacy --metadata-file path
    # routes to the original CSV-backed query_metadata for back-compat.
    if args.sql is not None:
        orchestrator = _build_orchestrator(args, require_minio=False)
        df = orchestrator.query(sql=args.sql)
        print(df.to_csv(index=False))
        return 0
    orchestrator = _build_orchestrator(args)
    filters = _parse_filters(args.filter)
    df = orchestrator.query_metadata(
        metadata_file=args.metadata_file,
        filters=filters or None,
        limit=args.limit,
    )
    print(df.to_csv(index=False))
    return 0


def _cmd_retrieve(args: argparse.Namespace) -> int:
    orchestrator = _build_orchestrator(args)
    filters = _parse_filters(args.filter)
    results: List[Dict[str, Any]] = orchestrator.retrieve_data(
        dataset=args.dataset,
        metadata_file=args.metadata_file,
        max_files=args.max_files,
        **filters,
    )
    success = sum(1 for r in results if r.get("success"))
    print(
        json.dumps(
            {"requested": len(results), "downloaded": success}, indent=2
        )
    )
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datorcloud", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_upload = sub.add_parser("upload", help="Upload dataset directories to MinIO.")
    p_upload.add_argument(
        "--dataset",
        action="append",
        required=True,
        help="Dataset spec NAME=PATH. May be repeated.",
    )
    _add_common_args(p_upload)
    p_upload.set_defaults(func=_cmd_upload)

    p_meta = sub.add_parser(
        "metadata", help="Generate metadata for datasets and upload to MinIO."
    )
    p_meta.add_argument("--dataset", action="append", required=True)
    p_meta.add_argument(
        "--output-file",
        default=os.path.join(
            _env_path("DATA_LAKE_PATH", "./data_lake"), "metadata.csv"
        ),
    )
    p_meta.add_argument("--object-name", default="metadata.csv")
    _add_common_args(p_meta)
    p_meta.set_defaults(func=_cmd_metadata)

    p_query = sub.add_parser(
        "query",
        help=(
            "Query the catalog. Use --sql for the Phase-1 L1-L4 path or "
            "--metadata-file for the legacy CSV path."
        ),
    )
    p_query.add_argument(
        "--sql",
        default=None,
        help=(
            "Raw DuckDB SQL evaluated against the Phase-1 L1-L4 catalog "
            "views (v_doris, v_doris_egress)."
        ),
    )
    p_query.add_argument("--metadata-file", default=None)
    p_query.add_argument("--filter", action="append", default=[])
    p_query.add_argument("--limit", type=int, default=None)
    _add_common_args(p_query)
    p_query.set_defaults(func=_cmd_query)

    p_retrieve = sub.add_parser("retrieve", help="Retrieve matching objects locally.")
    p_retrieve.add_argument("--dataset", required=True)
    p_retrieve.add_argument("--metadata-file", default=None)
    p_retrieve.add_argument("--filter", action="append", default=[])
    p_retrieve.add_argument("--max-files", type=int, default=None)
    _add_common_args(p_retrieve)
    p_retrieve.set_defaults(func=_cmd_retrieve)

    p_version = sub.add_parser("version", help="Print the installed datorcloud version.")
    p_version.set_defaults(func=_cmd_version, verbose=0)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", 0))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
