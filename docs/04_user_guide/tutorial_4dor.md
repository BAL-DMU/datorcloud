# Tutorial — Using DatorCloud with the 4dor-dataset

This tutorial takes you **from a fresh clone of the repository** to a fully
working DatorCloud pipeline on the bundled `4dor-dataset`, a multi-camera
surgical recording:

```
4dor-dataset/
├── experiment-1/
│   ├── camera01/
│   │   ├── colorimage/  camera01_colorimage-000031.jpg, ...
│   │   └── depthimage/  camera01_depthimage-000031.tiff, ...
│   ├── camera02/ ... camera06/
└── experiment-2/
    └── (same structure)
```

You will:

1. Build and start the Docker stack (MinIO, DuckDB, Dagster, DatorCloud CLI, Python runner).
2. Upload the dataset to **MinIO** (Object Store).
3. Generate **L2 metadata** and persist it as a CSV in MinIO.
4. Query the metadata with **DuckDB** through `s3://`.
5. Download a filtered subset back to the local filesystem.

> **Convention used in this tutorial**
>
> Every command block is prefixed with the shell where it must be run:
>
> | Prefix                                    | Where it runs                                              |
> | :---------------------------------------- | :--------------------------------------------------------- |
> | `host$`                                   | Your Windows host (PowerShell or any shell)                |
> | `cli#`                                    | Inside the **`datorcloud-cli`** container                  |
> | `runner#`                                 | Inside the **`python-runner`** container                   |

---

## Step 0 — Prerequisites

| Requirement                  | Notes                                                                 |
| :--------------------------- | :-------------------------------------------------------------------- |
| Docker Desktop + Docker Compose v2 | The whole stack runs in containers; nothing must be installed on the host. |
| `git`                        | To clone the repository.                                              |
| `4dor-dataset` on disk       | Placed under `${DATA_LAKE_PATH}/4dor-dataset` (default: `./dataspaces/data_lake/4dor-dataset`). |
| Free local ports             | **9090** (MinIO API), **9091** (MinIO Console), **3030** (Dagster), **5825** (DuckDB). |

### Storage layout

All project storage lives under a single host directory defined by
`PROJECT_ROOT` in `.env` (default `./dataspaces`):

```
${PROJECT_ROOT}/
├── data_lake/        ← raw datasets you want to ingest  (mount → /app/data_lake)
├── data_warehouse/   ← MinIO's bucket-backing storage   (mount → /data inside minio)
└── retrieved_data/   ← download target for `retrieve`   (mount → /app/retrieved_data)
```

Override individual paths by setting `DATA_LAKE_PATH`, `DATA_WAREHOUSE_PATH`,
or `RETRIEVED_DATA_PATH` in `.env`.

---

## Step 1 — Clone, configure, and build the stack

```bash
host$ git clone https://github.com/jagh/datorcloud.git
host$ cd datorcloud
host$ cp .env.example .env       # then edit paths if you want
host$ docker compose up -d --build
```

Wait until all five services are **Up**:

```bash
host$ docker compose ps
```

Expected output (abridged):

```
NAME             SERVICE          STATUS    PORTS
dagster          dagster          Up        0.0.0.0:3030->3030/tcp
datorcloud-cli   datorcloud-cli   Up
duckdb           duckdb           Up        0.0.0.0:5825->5825/tcp
minio            minio            Up        0.0.0.0:9090-9091->9090-9091/tcp
python-runner    python-runner    Up
```

### Sanity checks

```bash
# MinIO Console (should return HTTP 200)
host$ curl -I http://127.0.0.1:9091

# MinIO S3 API
host$ curl -I http://127.0.0.1:9090

# Dataset is mounted inside the CLI container
host$ docker exec datorcloud-cli ls /app/data_lake/4dor-dataset
# experiment-1
# experiment-2

# CLI is reachable inside the CLI container
host$ docker exec datorcloud-cli python -m datorcloud.cli version
```

Open the MinIO Console in your browser at <http://127.0.0.1:9091> and log in
with the credentials defined in `.env` (defaults: `minioadmin` / `minioadmin`).

!!! warning "MinIO ports are 9090 / 9091, **not** 9000 / 9001"
    This compose file remaps MinIO so it does not collide with other local
    services. Forget the upstream defaults.

!!! note "About the CLI invocation"
    The current `datorcloud-cli` image does not yet register the short
    `datorcloud` console script on `PATH`. The supported invocation today is
    `python -m datorcloud.cli ...` (run from `/app`, which is the default
    working directory). Both forms accept identical arguments.

---

## Step 2 — Upload the dataset to MinIO

### Option A — CLI (inside the `datorcloud-cli` container)

The CLI ships in the **`datorcloud-cli`** image (`jagh1729/datorcloud-cli:latest`).
Inside the container the dataset lives at `/app/data_lake/4dor-dataset`:

```bash
host$ docker exec -it datorcloud-cli python -m datorcloud.cli upload \
        --dataset 4dor-dataset=/app/data_lake/4dor-dataset \
        --minio-endpoint minio:9090 \
        -v
```

Expected output:

```json
{
  "4dor-dataset": 48
}
```

(48 = 2 experiments × 6 cameras × 2 modalities × 2 frames in the repo sample.)

### Option B — Python (inside the `python-runner` container or your host)

Inside the **`python-runner`** container (`jagh1729/dms-python-service:latest`):

```bash
host$ docker exec -it python-runner bash
runner# python
```

```python
from datorcloud import MinioObjectComponent

minio = MinioObjectComponent(
    endpoint="minio:9090",          # container-internal hostname
    access_key="minioadmin",
    secret_key="minioadmin",
)

minio.ensure_bucket_exists("orx-datalake")

results = minio.upload_directory(
    local_directory="/app/data_lake/4dor-dataset",
    bucket_name="orx-datalake",
    prefix="4dor-dataset",
)
print(f"{sum(r['status'] == 'success' for r in results)} files uploaded")
```

If you prefer to run Python on your **host** (after `pip install -e ".[dagster,test]"`),
use `endpoint="localhost:9090"` and `local_directory="./dataspaces/data_lake/4dor-dataset"`.

### Verify the upload in MinIO

Open <http://127.0.0.1:9091> → bucket **`orx-datalake`**. You should see:

```
4dor-dataset/experiment-1/camera01/colorimage/camera01_colorimage-000031.jpg
4dor-dataset/experiment-1/camera01/depthimage/camera01_depthimage-000031.tiff
...
```

---

## Step 3 — Generate L2 metadata and store it in MinIO

`MetadataGeneratorComponent` walks the tree and emits one row per file with
auto-extracted fields: `dataset`, `experiment`, `subfolder`, `file_name`,
`file_path`, `file_format`, `camera_id`, `image_type`, `frame_number`.

### Option A — CLI (inside `datorcloud-cli`)

```bash
host$ docker exec -it datorcloud-cli python -m datorcloud.cli metadata \
        --dataset 4dor-dataset=/app/data_lake/4dor-dataset \
        --output-file /app/data_lake/metadata_4dor.csv \
        --object-name metadata_4dor.csv \
        --minio-endpoint minio:9090 \
        -v
```

Expected output:

```json
{
  "records": 48,
  "output_file": "/app/data_lake/metadata_4dor.csv"
}
```

The CSV is now stored **locally** (in the mounted `data/` folder on your
host) **and** at `s3://orx-metadata/metadata_4dor.csv`.

### Option B — Python (inside `python-runner`)

```python
from datorcloud import MetadataGeneratorComponent, MetadataStorageComponent

generator = MetadataGeneratorComponent()
storage = MetadataStorageComponent(
    minio_component=minio,                # reuse the client from Step 2
    metadata_bucket="orx-metadata",
)

metadata_df = storage.create_metadata_and_store(
    metadata_generator_component=generator,
    dataset_dirs={"4dor-dataset": "/app/data_lake/4dor-dataset"},
    local_file_path="/app/data_lake/metadata_4dor.csv",
    object_name="metadata_4dor.csv",
)

print(metadata_df.head())
```

Sample row:

| dataset      | experiment   | subfolder           | file_name                       | camera_id | image_type | frame_number |
| ------------ | ------------ | ------------------- | ------------------------------- | --------- | ---------- | ------------ |
| 4dor-dataset | experiment-1 | camera01/colorimage | camera01_colorimage-000031.jpg  | camera01  | colorimage | 31           |

---

## Step 4 — Query the metadata with DuckDB

DuckDB reads the CSV directly from MinIO over `httpfs`, so the metadata
bucket behaves like a remote analytical table.

### Option A — CLI (inside `datorcloud-cli`)

```bash
# All camera01 color frames, first 10
host$ docker exec -it datorcloud-cli python -m datorcloud.cli query \
        --metadata-file s3://orx-metadata/metadata_4dor.csv \
        --filter camera_id=camera01 \
        --filter image_type=colorimage \
        --limit 10 \
        --s3-endpoint minio:9090
```

The CLI prints the result as CSV to stdout. Pipe it to a file with `>` if you
want to save it.

### Option B — Python (inside `python-runner`)

```python
from datorcloud import QueryComponent

query = QueryComponent(
    s3_endpoint="minio:9090",
    s3_access_key="minioadmin",
    s3_secret_key="minioadmin",
)

df = query.query_metadata(
    metadata_file="s3://orx-metadata/metadata_4dor.csv",
    filters={"camera_id": ["camera01", "camera02"], "frame_number": 31},
    limit=20,
)
print(df)
```

### Useful filter recipes

| Goal                                            | Filter expression                                                           |
| :---------------------------------------------- | :-------------------------------------------------------------------------- |
| All depth frames                                | `--filter image_type=depthimage`                                            |
| One specific frame across all sensors           | `--filter frame_number=31`                                                  |
| Color frames from cameras 1–3, experiment 1     | CLI: repeat `--filter camera_id=cameraNN` for each camera, plus `--filter experiment=experiment-1 --filter image_type=colorimage`. Python: `filters={"camera_id": ["camera01","camera02","camera03"], "experiment": "experiment-1", "image_type": "colorimage"}` |

---

## Step 5 — Retrieve the matching objects

`ObjectRetrievalComponent` re-runs the query, resolves object keys, and
downloads the files into `/app/retrieved_data/` inside the container (which
maps to `RETRIEVED_DATA_PATH` on your host, set in `.env`).

### Option A — CLI (inside `datorcloud-cli`)

```bash
host$ docker exec -it datorcloud-cli python -m datorcloud.cli retrieve \
        --dataset       4dor-dataset \
        --metadata-file s3://orx-metadata/metadata_4dor.csv \
        --filter        camera_id=camera01 \
        --filter        image_type=colorimage \
        --max-files     5 \
        --minio-endpoint minio:9090 \
        --local-dir     /app/retrieved_data \
        -v
```

Expected output:

```json
{
  "requested": 4,
  "downloaded": 4
}
```

On your host, the files now appear at:

```
${RETRIEVED_DATA_PATH}/4dor-dataset/experiment-1/camera01/colorimage/
${RETRIEVED_DATA_PATH}/4dor-dataset/experiment-2/camera01/colorimage/
```

### Option B — Python (inside `python-runner`)

```python
from datorcloud import ObjectRetrievalComponent

retrieval = ObjectRetrievalComponent(
    minio_component=minio,
    query_component=query,
    local_base_dir="/app/retrieved_data",
)

downloaded = retrieval.retrieve_objects(
    metadata_file="s3://orx-metadata/metadata_4dor.csv",
    dataset="4dor-dataset",
    data_bucket="orx-datalake",
    camera_id="camera01",
    image_type="colorimage",
    max_files=5,
)
for f in downloaded:
    print(f["success"], f["local_path"])
```

---

## Step 6 — One-call alternative (orchestrator)

If you do not want to assemble the components yourself, the orchestrator
exposes the same four stages from a single class. Run it inside
`python-runner`:

```python
from datorcloud.core import DatorCloudOrchestrator

orch = DatorCloudOrchestrator(
    minio_endpoint="minio:9090",
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)

orch.upload_datasets({"4dor-dataset": "/app/data_lake/4dor-dataset"})

orch.generate_and_upload_metadata(
    dataset_dirs={"4dor-dataset": "/app/data_lake/4dor-dataset"},
    output_file="/app/data_lake/metadata_4dor.csv",
    object_name="metadata_4dor.csv",
)

orch.query_metadata(
    metadata_file="s3://orx-metadata/metadata_4dor.csv",
    filters={"camera_id": "camera01"},
    limit=10,
)

orch.retrieve_data(
    dataset="4dor-dataset",
    metadata_file="s3://orx-metadata/metadata_4dor.csv",
    camera_id="camera01",
    image_type="colorimage",
    max_files=5,
)
```

---

## Step 7 — (Optional) Run the pipeline as a Dagster job

The compose stack already runs a Dagster webserver on **port 3030**. Open
<http://127.0.0.1:3030>, select **`datorcloud_workflow_job`**, click
**Launchpad**, and paste:

```yaml
resources:
  datorcloud:
    config:
      minio_endpoint: minio:9090
      access_key: minioadmin
      secret_key: minioadmin
      data_bucket: orx-datalake
      metadata_bucket: orx-metadata
ops:
  upload_datasets:
    config:
      dataset_paths:
        4dor-dataset: /app/data_lake/4dor-dataset
  generate_metadata:
    config:
      dataset_dirs:
        4dor-dataset: /app/data_lake/4dor-dataset
      output_file: /app/data_lake/metadata_4dor.csv
      object_name: metadata_4dor.csv
  query_metadata:
    config:
      filters:
        camera_id: camera01
        image_type: colorimage
      limit: 10
  retrieve_objects:
    config:
      dataset: 4dor-dataset
      filters:
        camera_id: camera01
        image_type: colorimage
      max_files: 5
```

Materialize the four assets in order; each pill turns green when it completes.

---

## Troubleshooting

| Symptom                                           | Cause / Fix                                                                                       |
| :------------------------------------------------ | :------------------------------------------------------------------------------------------------ |
| Browser cannot connect to `127.0.0.1:9000/9001`   | Wrong ports. This stack uses **9090** (API) and **9091** (Console).                               |
| `Failed to resolve 'minio'` from the host         | The `minio` hostname only exists *inside* the Compose network. From the host, use `localhost:9090`. |
| `AccessDenied` on upload / query                  | Mismatch between `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` and `S3_ACCESS_KEY`/`S3_SECRET_KEY` in `.env`. Set both pairs to the same values. |
| `datorcloud: not found` inside the container      | The current image does not register the console script. Use `python -m datorcloud.cli ...` instead, or rebuild the image. |
| `Could not load DuckDB httpfs extension`          | Pass `--duckdb-extension-path /path/to/httpfs.duckdb_extension` or set `DUCKDB_HTTPFS_EXTENSION_PATH` in the container's environment. |
| Empty query result                                | The metadata CSV lives in `orx-metadata`, **not** `orx-datalake`. Confirm the URL is `s3://orx-metadata/metadata_4dor.csv`. |
| `404 NoSuchKey` during retrieve                   | Step 2 (upload) did not complete; re-run the upload step.                                          |
| Dagster page does not load                        | Check that port **3030** is free on the host and that the `dagster` container is `Up`.            |

---

## Next steps

- [Python API](python_api.md) — full component reference.
- [CLI](cli.md) — all subcommands and flags.
- [Dagster Integration](dagster.md) — `DatorCloudResource` and the four assets.
- [Architecture](../03_components/architecture.md) — how the L1–L4 model maps onto the components.
