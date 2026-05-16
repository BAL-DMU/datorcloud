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
| `--local-download-dir`        | `$RETRIEVED_DATA_PATH` or `./retrieved_data` | Where `retrieve` writes files.       |
| `--duckdb-extension-path`     | _auto_                                 | Explicit `httpfs.duckdb_extension` path. |
| `-v / -vv`                    | warnings                               | Increase log verbosity.                  |

## Subcommands

### `datorcloud upload`

Upload one or more dataset directories to MinIO.

```bash
datorcloud upload --dataset 4dor-dataset=./dataspaces/data_lake/4dor-dataset \
                  --dataset orx-experiments=./dataspaces/data_lake/orx-experiments
```

`--dataset` may be repeated. The output is a JSON map of `{dataset: file_count}`.

### `datorcloud metadata`

Generate metadata for the configured datasets and upload the resulting CSV.

```bash
datorcloud metadata --dataset 4dor-dataset=./dataspaces/data_lake/4dor-dataset \
                    --output-file ./dataspaces/data_lake/metadata.csv \
                    --object-name metadata.csv
```

The default `--output-file` is `${DATA_LAKE_PATH}/metadata.csv` when
`DATA_LAKE_PATH` is set in the environment (or `./data_lake/metadata.csv`
otherwise).

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

The `python-runner` and `datorcloud-cli` services in `docker-compose.yml`
already have the package installed and inherit the `S3_*`, `DATA_LAKE_PATH`,
and `RETRIEVED_DATA_PATH` environment variables. Inside both containers the
dataset lake is mounted at `/app/data_lake`:

```bash
docker exec -it datorcloud-cli python -m datorcloud.cli upload \
    --dataset 4dor-dataset=/app/data_lake/4dor-dataset
```

!!! note
    The current `datorcloud-cli` image does not yet register the short
    `datorcloud` console script on `PATH`. Use `python -m datorcloud.cli ...`
    until the image is rebuilt.
