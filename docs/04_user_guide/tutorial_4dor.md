# Tutorial — Using DatorCloud with the 4dor-dataset

This tutorial walks the bundled example
[`examples/datorcloud_basic_usage.py`](https://github.com/jagh/datorcloud/blob/datorcloud-component/examples/datorcloud_basic_usage.py)
end-to-end. The script materialises the two operational workflows from the
[DatorCloud architecture diagram](../03_components/architecture.md):

| Workflow                | Pipeline                                                                                                                              |
| :---------------------- | :------------------------------------------------------------------------------------------------------------------------------------ |
| **A - Ingestion**       | device / sensor data → Object Store (MinIO) → Metadata Generation → NoSQL Metadata Store → Database Catalog Update                    |
| **B - Query & Fetch**   | filter specification → QueryComponent (DuckDB) over L1–L4 → Matched Metadata Records → Object Retrieval → Local Filesystem Export     |

The sample input is the bundled `4dor-dataset`, a multi-camera surgical
recording:

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

The layout mirrors multi-camera **RGB** and **depth** recordings from the
[**4D-OR** project](https://github.com/egeozsoy/4D-OR) (semantic scene graphs
for the operating room). The repository ships a small **dev slice** of that
family of data as `4dor-dataset`; for the full dataset, evaluation splits,
and licence terms, use the official repo above.

> **Convention used in this tutorial**
>
> Every command block is prefixed with the shell where it must be run:
>
> | Prefix      | Where it runs                                              |
> | :---------- | :--------------------------------------------------------- |
> | `host$`     | Your Windows host (PowerShell or any shell)                |
> | `cli#`      | Inside the **`datorcloud-cli`** container                  |
> | `runner#`   | Inside the **`python-runner`** container                   |

---

## Step 0 — Prerequisites

| Requirement                          | Notes                                                                 |
| :----------------------------------- | :-------------------------------------------------------------------- |
| Docker Desktop + Docker Compose v2   | The whole stack runs in containers; nothing extra on the host.        |
| `git`                                | To clone the repository.                                              |
| `4dor-dataset` on disk               | Placed under `${DATA_LAKE_PATH}/4dor-dataset` (default: `./dataspaces/data_lake/4dor-dataset`). |
| Free local ports                     | **9090** (MinIO API), **9091** (MinIO Console), **3030** (Dagster). DuckDB runs as a distroless CLI image and does not expose a port. |

### Storage layout

All project storage lives under a single host directory defined by
`PROJECT_ROOT` in `.env` (default `./dataspaces`):

```
${PROJECT_ROOT}/
├── data_lake/        ← raw datasets you want to ingest  (mount → /app/data_lake)
├── data_warehouse/   ← MinIO's bucket-backing storage   (mount → /data inside minio)
└── retrieved_data/   ← download target for Workflow B   (mount → /app/retrieved_data)
```

Override individual paths by setting `DATA_LAKE_PATH`, `DATA_WAREHOUSE_PATH`,
or `RETRIEVED_DATA_PATH` in `.env`.

---

## Step 1 — Clone, configure, and build the stack

```bash
host$ git clone https://github.com/jagh/datorcloud.git
host$ cd datorcloud
host$ cp .env.example .env       # then edit S3_ACCESS_KEY / S3_SECRET_KEY
host$ docker compose up -d --build
```

Wait until all five services are **Up**:

```bash
host$ docker compose ps
```

Expected (abridged):

```
NAME             SERVICE          STATUS    PORTS
dagster          dagster          Up        0.0.0.0:3030->3030/tcp
datorcloud-cli   datorcloud-cli   Up
duckdb           duckdb           Up
minio            minio            Up        0.0.0.0:9090-9091->9090-9091/tcp
python-runner    python-runner    Up
```

### Sanity checks

```bash
# MinIO Console (200 OK)
host$ curl.exe -I http://127.0.0.1:9091
# MinIO S3 API   (200 / 403 — both prove the API responded)
host$ curl.exe -I http://127.0.0.1:9090
# 4dor-dataset visible inside the CLI container
host$ docker exec datorcloud-cli ls /app/data_lake/4dor-dataset
# CLI is installed (returns the package version, e.g. 0.1.0)
host$ docker exec datorcloud-cli python -m datorcloud.cli version
```

Open the MinIO Console at <http://127.0.0.1:9091> and log in with the
credentials you put into `.env`.

!!! note "Windows PowerShell users"
    `curl` in PowerShell is an alias for `Invoke-WebRequest` and does not
    accept `-I`. Either call the real binary as `curl.exe -I ...` (shown
    above) or use `Invoke-WebRequest -Uri http://127.0.0.1:9091 -Method Head`.

!!! warning "MinIO ports are 9090 / 9091, **not** 9000 / 9001"
    This compose file remaps MinIO so it does not collide with other local
    services. Forget the upstream defaults.

---

## Step 2 — Run both workflows in one shot

The `python-runner` container runs `pip install --quiet -e /app` on
startup (see its `command:` in `docker-compose.yml`), so the bind-mounted
`datorcloud` package is importable from any path and every
`S3_*`/`DATA_LAKE_PATH`/`RETRIEVED_DATA_PATH` variable is inherited from
the project `.env`. Running the bundled example executes **Workflow A
followed by Workflow B** without any further configuration:

```bash
host$ docker exec -it python-runner python /app/examples/datorcloud_basic_usage.py
```

!!! tip "First run after `docker compose up`"
    The editable install adds ~10 s to the first container start. If you
    see `ModuleNotFoundError: No module named 'datorcloud'`, the
    `pip install` has not finished yet — wait a few seconds and re-run,
    or trigger it manually with `docker exec python-runner pip install -e /app`.

Expected (abridged) log output — the bracketed banners come straight from
the script and mirror the architecture diagram:

```
INFO datorcloud.examples.basic: === Workflow A — Ingestion ===
INFO datorcloud.examples.basic: [Workflow A · Stage 1/5] device / sensor data — resolving local dataset paths from .env
INFO datorcloud.examples.basic:   ✓ 4dor-dataset → /app/data_lake/4dor-dataset
INFO datorcloud.examples.basic: [Workflow A · Stage 2/5] Object Store (MinIO) — uploading raw objects to bucket 'orx-datalake'
INFO datorcloud.examples.basic:   → 48 object(s) uploaded across 1 dataset(s).
INFO datorcloud.examples.basic: [Workflow A · Stage 3/5] Metadata Generation — extracting L2 sensor metadata
INFO datorcloud.examples.basic:   → 48 L2 sensor-metadata record(s) across 1 dataset(s).
INFO datorcloud.examples.basic: [Workflow A · Stage 4/5] NoSQL Metadata Store — persisting L2/L3 + L4 to bucket 'orx-metadata'
INFO datorcloud.examples.basic:   → metadata written to /app/data_lake/metadata_4dor.csv and to s3://orx-metadata/metadata_4dor.csv
INFO datorcloud.examples.basic: [Workflow A · Stage 5/5] Database Catalog Update — registering L1 Experiment Card + L4 Dataset Card in DuckDB
INFO datorcloud.examples.basic:   → DuckDB catalog refreshed: 2 row(s) in experiment_card (L1), 1 row(s) in dataset_card (L4).

INFO datorcloud.examples.basic: === Workflow B — Query & Fetch ===
INFO datorcloud.examples.basic: [Workflow B · Stage 1/5] Filter specification — {'camera_id': 'camera01'} (limit=10)
INFO datorcloud.examples.basic: [Workflow B · Stage 2/5] QueryComponent (DuckDB) — querying L1–L4 via s3://orx-metadata/metadata_4dor.csv
INFO datorcloud.examples.basic: [Workflow B · Stage 3/5] Matched Metadata Records — 4 row(s)
INFO datorcloud.examples.basic: [Workflow B · Stage 4/5] Object Retrieval — fetching dataset '4dor-dataset' / experiment 'experiment-1' from MinIO
INFO datorcloud.examples.basic:   → 4/4 object(s) retrieved.
INFO datorcloud.examples.basic: [Workflow B · Stage 5/5] Local Filesystem Export — files materialised under /app/retrieved_data
```

(The exact object counts depend on the dataset slice you placed in
`${DATA_LAKE_PATH}/4dor-dataset`. The repo sample is 2 experiments × 6
cameras × 2 modalities × 2 frames = **48 objects**.)

The next two sections narrate each stage and tell you how to verify it.

---

## Step 3 — Workflow A: Ingestion (5 stages)

### Stage 1/5 — device / sensor data

The script reads `DATA_LAKE_PATH` from `.env` and resolves
`${DATA_LAKE_PATH}/4dor-dataset` on disk:

```python
dataset_paths = {"4dor-dataset": os.path.join(data_lake, "4dor-dataset")}
```

**Verify:** the banner prints `✓ 4dor-dataset → /app/data_lake/4dor-dataset`.
A missing folder is reported as `✗ ... (missing on disk, skipping)` and the
workflow aborts with a clear `RuntimeError`.

### Stage 2/5 — Object Store (MinIO)

`MinioObjectComponent.upload_directory(...)` recursively uploads the
dataset to the `orx-datalake` bucket under the `4dor-dataset/` prefix.

```python
minio.ensure_bucket_exists("orx-datalake")
minio.upload_directory(
    local_directory="/app/data_lake/4dor-dataset",
    bucket_name="orx-datalake",
    prefix="4dor-dataset",
)
```

**Verify:** open <http://127.0.0.1:9091> → bucket **`orx-datalake`**. You
should see:

```
4dor-dataset/experiment-1/camera01/colorimage/camera01_colorimage-000031.jpg
4dor-dataset/experiment-1/camera01/depthimage/camera01_depthimage-000031.tiff
...
```

### Stage 3/5 — Metadata Generation

`MetadataGeneratorComponent.generate_metadata(...)` walks the dataset tree
and emits one **L2 sensor-metadata** row per file, with auto-extracted
fields: `dataset`, `experiment`, `subfolder`, `file_name`, `file_path`,
`file_format`, `camera_id`, `image_type`, `frame_number`.

```python
metadata_df = generator.generate_metadata(dataset_dirs=resolved)
```

Sample row:

| dataset      | experiment   | subfolder           | file_name                       | camera_id | image_type | frame_number |
| :----------- | :----------- | :------------------ | :------------------------------ | :-------- | :--------- | :----------- |
| 4dor-dataset | experiment-1 | camera01/colorimage | camera01_colorimage-000031.jpg  | camera01  | colorimage | 31           |

### Stage 4/5 — NoSQL Metadata Store

`MetadataStorageComponent.store_metadata(...)` persists the DataFrame from
Stage 3 in two places: locally as `metadata_4dor.csv` and inside the
`orx-metadata` MinIO bucket (which acts as the NoSQL store via DuckDB's
`httpfs`):

```python
storage.store_metadata(
    metadata_df=metadata_df,
    local_file_path="/app/data_lake/metadata_4dor.csv",
    bucket_name="orx-metadata",
    object_name="metadata_4dor.csv",
)
```

**Verify:** in the MinIO Console, switch to bucket **`orx-metadata`**. You
should see a single object `metadata_4dor.csv`. Download it to spot-check
the L2 rows.

### Stage 5/5 — Database Catalog Update

The DuckDB connection embedded in `QueryComponent` registers two tables
that serve as the **L1 Experiment Card** and **L4 Dataset Card** catalog:

```python
query.conn.execute("""
    CREATE OR REPLACE TABLE experiment_card AS
    SELECT dataset, experiment,
           COUNT(*)                   AS file_count,
           COUNT(DISTINCT camera_id)  AS sensor_count,
           COUNT(DISTINCT image_type) AS modality_count
    FROM read_csv_auto('/app/data_lake/metadata_4dor.csv')
    GROUP BY dataset, experiment
""")

query.conn.execute("""
    CREATE OR REPLACE TABLE dataset_card AS
    SELECT dataset,
           COUNT(DISTINCT experiment) AS experiment_count,
           COUNT(*)                   AS file_count,
           COUNT(DISTINCT camera_id)  AS sensor_count
    FROM read_csv_auto('/app/data_lake/metadata_4dor.csv')
    GROUP BY dataset
""")
```

**Verify:** the banner reports the row count of each table — for the
bundled dataset that is **2 rows in `experiment_card`** (L1, one per
experiment) and **1 row in `dataset_card`** (L4, summarising the full
dataset).

---

## Step 4 — Workflow B: Query & Fetch (5 stages)

### Stage 1/5 — Filter specification

The script's `main()` passes a filter dict to `run_query_and_fetch_workflow`:

```python
filters = {"camera_id": "camera01"}
```

Other useful filters:

| Goal                                              | Filter expression                                                       |
| :------------------------------------------------ | :---------------------------------------------------------------------- |
| All depth frames                                  | `{"image_type": "depthimage"}`                                          |
| One frame across all sensors                      | `{"frame_number": 31}`                                                  |
| Color frames from cameras 1–3 in experiment 1     | `{"camera_id": ["camera01", "camera02", "camera03"], "experiment": "experiment-1", "image_type": "colorimage"}` |

Lists become SQL `IN (...)` clauses; scalars become `=` clauses.

### Stage 2/5 — QueryComponent (DuckDB) over L1–L4

`QueryComponent.query_metadata(...)` reads the metadata CSV directly from
MinIO over `s3://` and applies the filter through DuckDB:

```python
results = query.query_metadata(
    metadata_file="s3://orx-metadata/metadata_4dor.csv",
    filters={"camera_id": "camera01"},
    limit=10,
)
```

The `httpfs` extension is loaded automatically when `QueryComponent` is
constructed; the S3 endpoint and credentials come from `.env`.

### Stage 3/5 — Matched Metadata Records

The script logs the row count and a 5-row preview of the canonical L2
columns:

```
INFO datorcloud.examples.basic:   preview (first 4 row(s)):
 dataset      experiment   camera_id image_type frame_number                       file_name
 4dor-dataset experiment-1 camera01  colorimage           31  camera01_colorimage-000031.jpg
 4dor-dataset experiment-1 camera01  depthimage           31  camera01_depthimage-000031.tiff
 ...
```

If the query is empty the workflow logs a warning and skips the remaining
stages — useful for fast filter iteration without raising.

### Stage 4/5 — Object Retrieval

`ObjectRetrievalComponent.retrieve_experiment_data(...)` re-runs the
query, resolves the S3 object keys, and downloads every matching file:

```python
downloaded = retrieval.retrieve_experiment_data(
    metadata_file="s3://orx-metadata/metadata_4dor.csv",
    dataset="4dor-dataset",
    experiment="experiment-1",          # taken from results.iloc[0]
    data_bucket="orx-datalake",
    camera_id="camera01",
)
```

The script reports `successes / total`, so partial failures (e.g. an
object missing in MinIO) are visible without aborting the run.

### Stage 5/5 — Local Filesystem Export

Files are materialised under `RETRIEVED_DATA_PATH` (= `/app/retrieved_data`
inside the container, mapped to your host's `./dataspaces/retrieved_data`):

```
${RETRIEVED_DATA_PATH}/4dor-dataset/experiment-1/camera01/colorimage/
    camera01_colorimage-000031.jpg
```

**Verify on the host:**

```bash
host$ ls dataspaces/retrieved_data/4dor-dataset/experiment-1/camera01/colorimage/
```

---

## Step 5 — Equivalent CLI invocations (optional)

If you prefer shell-only, the four `datorcloud` subcommands map 1:1 to the
two workflows. Run them inside the `datorcloud-cli` container — it
inherits the same `.env`:

| Workflow stage(s)                  | CLI invocation                                                                                                                                                                                                                                |
| :--------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A · Stages 1–2**                 | `cli# python -m datorcloud.cli upload --dataset 4dor-dataset=/app/data_lake/4dor-dataset -v`                                                                                                                                                  |
| **A · Stages 3–4**                 | `cli# python -m datorcloud.cli metadata --dataset 4dor-dataset=/app/data_lake/4dor-dataset --output-file /app/data_lake/metadata_4dor.csv --object-name metadata_4dor.csv -v`                                                                  |
| **B · Stages 1–3**                 | `cli# python -m datorcloud.cli query --metadata-file s3://orx-metadata/metadata_4dor.csv --filter camera_id=camera01 --filter image_type=colorimage --limit 10`                                                                              |
| **B · Stages 4–5**                 | `cli# python -m datorcloud.cli retrieve --dataset 4dor-dataset --metadata-file s3://orx-metadata/metadata_4dor.csv --filter camera_id=camera01 --filter image_type=colorimage --max-files 5 --local-download-dir /app/retrieved_data -v`     |

Stage 5 of Workflow A (Database Catalog Update) is not currently exposed
through the CLI; use the Python example or open a DuckDB session against
the `metadata_4dor.csv` directly.

!!! note "About the CLI invocation"
    The current `datorcloud-cli` image does not yet register the short
    `datorcloud` console script on `PATH`. Use `python -m datorcloud.cli ...`
    until the image is rebuilt.

---

## Step 6 — Run the same pipeline as a Dagster job (optional)

The compose stack already runs a Dagster webserver on **port 3030**. Open
<http://127.0.0.1:3030>, select **`datorcloud_workflow_job`**, click
**Launchpad**, and paste:

```yaml
# Resource fields (endpoint, credentials, paths) default to the corresponding
# environment variables, which are loaded from the project .env. Only override
# what you want to change.
resources:
  datorcloud:
    config:
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

Materialize the four assets in order; each pill turns green when it
completes. The asset chain implements the same two workflows: `upload_datasets`
+ `generate_metadata` cover Workflow A's Stages 2–4, while `query_metadata`
+ `retrieve_objects` cover Workflow B.

---

## Troubleshooting

| Symptom                                            | Cause / Fix                                                                                                                                          |
| :------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RuntimeError: No dataset paths exist on disk`     | Workflow A · Stage 1 could not find `${DATA_LAKE_PATH}/4dor-dataset`. Place the dataset there or set `DATA_LAKE_PATH` in `.env`.                     |
| `RuntimeError: Required environment variable S3_ACCESS_KEY is not set` | The script could not read credentials from `.env`. Confirm `S3_ACCESS_KEY` / `S3_SECRET_KEY` are present and exported in the container's environment. |
| `ModuleNotFoundError: No module named 'datorcloud'` in `python-runner` | The bootstrap `pip install -e /app` did not complete (or you are on an older compose file). Run `docker exec python-runner pip install -e /app` once, then re-run the script. |
| `curl : Cannot find drive. A drive with the name 'http' does not exist.` | PowerShell aliases `curl` to `Invoke-WebRequest`, which rejects `-I`. Use `curl.exe -I ...` or `Invoke-WebRequest -Uri ... -Method Head`. |
| Browser cannot connect to `127.0.0.1:9000/9001`    | Wrong ports. This stack uses **9090** (API) and **9091** (Console).                                                                                  |
| `Failed to resolve 'minio'` from the host          | The `minio` hostname only exists *inside* the Compose network. From the host, use `localhost:9090`.                                                  |
| `AccessDenied` on upload / query                   | Mismatch between `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` and `S3_ACCESS_KEY`/`S3_SECRET_KEY` in `.env`. Set both pairs to the same values.            |
| `datorcloud: not found` inside the container       | The current image does not register the console script. Use `python -m datorcloud.cli ...` instead, or rebuild the image.                            |
| `Could not load DuckDB httpfs extension` / `Failed to deserialize: field id mismatch, expected: 100, got: NNNN` | The container has a stale/corrupt extension cache. `QueryComponent` now falls back to `FORCE INSTALL httpfs` automatically, but if it still fails wipe the cache once: `docker exec python-runner rm -rf /root/.duckdb/extensions` and re-run. Alternatively pass `--duckdb-extension-path /path/to/httpfs.duckdb_extension` or set `DUCKDB_HTTPFS_EXTENSION_PATH`. |
| Empty query result in Workflow B                   | The metadata CSV lives in `orx-metadata`, **not** `orx-datalake`. Confirm the URL is `s3://orx-metadata/metadata_4dor.csv`.                          |
| `404 NoSuchKey` during retrieve                    | Workflow A · Stage 2 (upload) did not complete; re-run the script.                                                                                   |
| Dagster page does not load                         | Check that port **3030** is free on the host and that the `dagster` container is `Up`.                                                               |

---

## Dataset citation — 4D-OR

This tutorial uses sample data aligned with the **4D-OR** dataset and
methodology. If you publish work that builds on that data or codebase,
please cite the MICCAI 2022 paper and link the canonical resources:

- **Paper:** Özsoy, E., Örnek, E. P., Eck, U., Czempiel, T., Tombari, F., &
  Navab, N. *4D-OR: Semantic Scene Graphs for OR Domain Modeling.*
  MICCAI 2022. [Springer chapter](https://link.springer.com/chapter/10.1007/978-3-031-16449-1_45).
- **Dataset & code:** [github.com/egeozsoy/4D-OR](https://github.com/egeozsoy/4D-OR)

Optional BibTeX (MICCAI):

```bibtex
@inproceedings{Ozsoy2022_4D_OR,
  title     = {4D-OR: Semantic Scene Graphs for OR Domain Modeling},
  author    = {Özsoy, Ege and Örnek, Evin Pınar and Eck, Ulrich and
               Czempiel, Tobias and Tombari, Federico and Navab, Nassir},
  booktitle = {International Conference on Medical Image Computing and
               Computer-Assisted Intervention},
  year      = {2022},
  publisher = {Springer}
}
```

---

## Next steps

- [Python API](python_api.md) — full component reference and `DatorCloudOrchestrator.from_env()`.
- [CLI](cli.md) — every subcommand and flag.
- [Dagster Integration](dagster.md) — `DatorCloudResource` and the four chained assets.
- [Architecture](../03_components/architecture.md) — how the L1–L4 data model maps onto the components.
