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

from . import __version__
from .core import DatorCloudOrchestrator

log = logging.getLogger("datorcloud.cli")


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


def _build_orchestrator(args: argparse.Namespace) -> DatorCloudOrchestrator:
    return DatorCloudOrchestrator(
        minio_endpoint=args.minio_endpoint,
        minio_access_key=args.minio_access_key,
        minio_secret_key=args.minio_secret_key,
        minio_secure=args.minio_secure,
        data_bucket=args.data_bucket,
        metadata_bucket=args.metadata_bucket,
        local_download_dir=args.local_download_dir,
        duckdb_extension_path=args.duckdb_extension_path,
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--minio-endpoint",
        default=os.environ.get("S3_ENDPOINT", "minio:9090").replace("http://", "").replace("https://", ""),
    )
    parser.add_argument("--minio-access-key", default=os.environ.get("S3_ACCESS_KEY", "minioadmin"))
    parser.add_argument("--minio-secret-key", default=os.environ.get("S3_SECRET_KEY", "minioadmin"))
    parser.add_argument("--minio-secure", action="store_true")
    parser.add_argument("--data-bucket", default="orx-datalake")
    parser.add_argument("--metadata-bucket", default="orx-metadata")
    parser.add_argument("--local-download-dir", default="./retrieved_data")
    parser.add_argument("--duckdb-extension-path", default=None)
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
    p_meta.add_argument("--output-file", default="./data/metadata.csv")
    p_meta.add_argument("--object-name", default="metadata.csv")
    _add_common_args(p_meta)
    p_meta.set_defaults(func=_cmd_metadata)

    p_query = sub.add_parser("query", help="Run a filtered query against the metadata CSV.")
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
