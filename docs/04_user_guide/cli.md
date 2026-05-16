# Command-Line Interface

The **DatorCloud framework** ships a `datorcloud` command, installed by
`pip install -e .`. It maps 1:1 to the orchestrator and is the recommended
way to drive the framework from shell scripts and from inside JupyterHub
terminals on **BAL-JH Spaces**.

## Global options

Every subcommand accepts:

| Flag                          | Default                                | Description                              |
| ----------------------------- | -------------------------------------- | ---------------------------------------- |
| `--minio-endpoint`            | `$S3_ENDPOINT` or `minio:9090`         | MinIO host:port (no scheme).             |
| `--minio-access-key`          | `$S3_ACCESS_KEY` or `minioadmin`       | MinIO access key.                        |
| `--minio-secret-key`          | `$S3_SECRET_KEY` or `minioadmin`       | MinIO secret key.                        |
| `--minio-secure`              | off                                    | Use HTTPS for MinIO.                     |
| `--data-bucket`               | `orx-datalake`                         | Bucket used for raw data.                |
| `--metadata-bucket`           | `orx-metadata`                         | Bucket used for the metadata CSV.        |
| `--local-download-dir`        | `./retrieved_data`                     | Where `retrieve` writes files.           |
| `--duckdb-extension-path`     | _auto_                                 | Explicit `httpfs.duckdb_extension` path. |
| `-v / -vv`                    | warnings                               | Increase log verbosity.                  |

## Subcommands

### `datorcloud upload`

Upload one or more dataset directories to MinIO.

```bash
datorcloud upload --dataset 4dor-dataset=./data/4dor-dataset \
                  --dataset orx-experiments=./data/orx-experiments
```

`--dataset` may be repeated. The output is a JSON map of `{dataset: file_count}`.

### `datorcloud metadata`

Generate metadata for the configured datasets and upload the resulting CSV.

```bash
datorcloud metadata --dataset 4dor-dataset=./data/4dor-dataset \
                    --output-file ./data/metadata.csv \
                    --object-name metadata.csv
```

### `datorcloud query`

Run a filtered query against the metadata CSV and print the result as CSV.

```bash
datorcloud query --filter camera_id=camera01 \
                 --filter image_type=colorimage \
                 --limit 10
```

`--filter` may be repeated; values are passed through as strings.
`--metadata-file` overrides the default `s3://<metadata-bucket>/metadata.csv`.

### `datorcloud retrieve`

Download every object matching a filter into `--local-download-dir`.

```bash
datorcloud retrieve --dataset 4dor-dataset \
                    --filter camera_id=camera01 \
                    --max-files 5
```

The output is a JSON summary `{"requested": N, "downloaded": M}`.

### `datorcloud version`

```bash
datorcloud version
# -> 0.1.0
```

## Running inside Docker

The `python-runner` and `datorcloud-cli` services in `docker-compose.yml` already
have the package installed and inherit the `S3_*` environment variables, so you
can use the CLI directly:

```bash
docker exec -it datorcloud-cli datorcloud upload \
    --dataset 4dor-dataset=/app/data/4dor-dataset
```
