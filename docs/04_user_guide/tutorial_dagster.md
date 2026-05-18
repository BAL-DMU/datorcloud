# Tutorial — DatorCloud Workflows in Dagster

This tutorial walks the bundled Dagster example
[`examples/datorcloud_dagster_workflow.py`](https://github.com/jagh/datorcloud/blob/datorcloud-component/examples/datorcloud_dagster_workflow.py)
end-to-end. The script materialises the two operational pipelines from the
[DatorCloud architecture diagram](../03_components/architecture.md) as
**two separate Dagster asset jobs**, both registered in `Definitions`:

| Job                              | Workflow                | Asset selection                                     | Diagram stages |
| :------------------------------- | :---------------------- | :-------------------------------------------------- | :------------- |
| `datorcloud_ingestion_job`       | **A — Ingestion**       | `upload_datasets`, `generate_metadata`, `catalog_update` | 5 stages       |
| `datorcloud_query_fetch_job`     | **B — Query & Fetch**   | `query_metadata`, `retrieve_objects`                | 5 stages       |

The reference page [Dagster Integration](dagster.md) describes
`DatorCloudResource` and the individual asset symbols; this tutorial focuses
on running the two jobs and reading the result.

> **Convention used in this tutorial**
>
> Every command block is prefixed with the shell where it must be run:
>
> | Prefix      | Where it runs                                              |
> | :---------- | :--------------------------------------------------------- |
> | `host$`     | Your Windows host (PowerShell or any shell)                |
> | `runner#`   | Inside the **`python-runner`** container                   |
> | `dagster#`  | Inside the **`dagster`** container                         |

---

## Step 0 — Prerequisites

| Requirement                          | Notes                                                                 |
| :----------------------------------- | :-------------------------------------------------------------------- |
| Stack up via `docker compose up -d`  | See [Tutorial — 4dor-dataset · Step 1](tutorial_4dor.md#step-1-clone-configure-and-build-the-stack) for the full setup. |
| `4dor-dataset` on disk               | Placed under `${DATA_LAKE_PATH}/4dor-dataset` (default `./dataspaces/data_lake/4dor-dataset`). |
| Editable install in `python-runner`  | Compose runs `pip install -e /app` on startup so `datorcloud` and the example are importable. |
| Free port 3030                       | Dagster webserver.                                                    |

The example reads every connection setting from the project `.env` through
`DatorCloudResource` — no credentials appear in the script or in the
launchpad YAML.

---

## Step 1 — Open the Dagster UI

The `dagster` service in `docker-compose.yml` already runs a webserver on
port **3030** and loads `workspace.yaml`, which points at
`examples/datorcloud_dagster_workflow.py`. Just open:

<http://127.0.0.1:3030>

You should see two jobs in the left-hand navigation:

- **`datorcloud_ingestion_job`** — Workflow A
- **`datorcloud_query_fetch_job`** — Workflow B

If you prefer to launch Dagster yourself (e.g. against a different
workspace), run from the host or inside the `dagster` container:

```bash
dagster# dagster dev -f /app/workspace/examples/datorcloud_dagster_workflow.py
```

---

## Step 2 — Run both jobs in one shot (in-process)

The example's `__main__` block executes Workflow A followed by Workflow B
in the same Python process, sharing an ephemeral Dagster instance and a
`FilesystemIOManager` so the second job can resolve the first job's
upstream materialisations:

```bash
host$ docker exec -it python-runner python /app/examples/datorcloud_dagster_workflow.py
```

Expected output:

```
=== Workflow A — Ingestion ===
... Dagster materialisation logs for upload_datasets / generate_metadata / catalog_update ...
Workflow A — Ingestion:    success

=== Workflow B — Query & Fetch ===
... Dagster materialisation logs for query_metadata / retrieve_objects ...
Workflow B — Query & Fetch: success
```

The next two sections explain the 5 stages each job covers and how to
launch them individually from the UI.

---

## Step 3 — Workflow A: Ingestion (5 stages)

Select **`datorcloud_ingestion_job`** in the Dagster UI and click
**Launchpad**. The launchpad opens **pre-filled** with the run config the
example bundles via `define_asset_job(config=...)`, so you can either hit
**Launch Run** as-is or edit the YAML below to customise paths and
buckets:

```yaml
ops:
  upload_datasets:
    config:
      # Stage 1/5 + 2/5 — device/sensor data → Object Store (MinIO)
      dataset_paths:
        4dor-dataset: /app/data_lake/4dor-dataset
      bucket_name: orx-datalake
  generate_metadata:
    config:
      # Stage 3/5 — Metadata Generation (L2 sensor metadata)
      dataset_dirs:
        4dor-dataset: /app/data_lake/4dor-dataset
      # Stage 4/5 — NoSQL Metadata Store (L2/L3 + L4 cards)
      output_file: /app/data_lake/metadata_4dor.csv
      bucket_name: orx-metadata
      object_name: metadata_4dor.csv
  catalog_update:
    config:
      # Stage 5/5 — Database Catalog Update (L1 + L4 in DuckDB)
      metadata_file: /app/data_lake/metadata_4dor.csv
```

Click **Launch Run**. The asset graph materialises in dependency order:

### Stage 1/5 — device / sensor data

The `dataset_paths` field tells `upload_datasets` which local directories
to ingest. Paths use the container-internal mount
`/app/data_lake/4dor-dataset`.

### Stage 2/5 — Object Store (MinIO) — `upload_datasets`

`upload_datasets` calls `MinioObjectComponent.upload_directory(...)`. The
asset's **Metadata** tab in the UI shows `total_files`, `successful_uploads`,
and `bucket`. Verify in the MinIO Console at
<http://127.0.0.1:9091> → bucket **`orx-datalake`**.

### Stage 3/5 — Metadata Generation — `generate_metadata`

`generate_metadata` invokes `MetadataGeneratorComponent.generate_metadata(...)`
to extract one **L2 sensor-metadata** row per file. The asset metadata
exposes `record_count`, `datasets`, and `columns`.

### Stage 4/5 — NoSQL Metadata Store — `generate_metadata`

The same asset persists the resulting DataFrame to
`/app/data_lake/metadata_4dor.csv` *and* to
`s3://orx-metadata/metadata_4dor.csv`. Verify in the MinIO Console →
bucket **`orx-metadata`**.

### Stage 5/5 — Database Catalog Update — `catalog_update`

`catalog_update` is the local asset added by the example. It opens a
DuckDB connection and runs `CREATE OR REPLACE TABLE` for both:

- **`experiment_card`** — the **L1 Experiment Card** (one row per
  `(dataset, experiment)`).
- **`dataset_card`** — the **L4 Dataset Card** (one row per dataset).

Row counts are emitted as Dagster `MetadataValue` and surface in the
asset's **Metadata** tab as `experiment_card_rows` and `dataset_card_rows`.

> **Note** — `DatorCloudResource.query` rebuilds an in-memory DuckDB
> connection on every property access, so the catalog tables live for the
> duration of this asset. The asset's role here is to demonstrate the
> ingestion pipeline's final stage and surface the L1/L4 statistics; for a
> persistent catalog, point `QueryComponent` at a DuckDB file on disk.

---

## Step 4 — Workflow B: Query & Fetch (5 stages)

Once Workflow A has run, select **`datorcloud_query_fetch_job`** in the
Dagster UI and open **Launchpad** — it again opens pre-filled with the
example's default config:

```yaml
ops:
  query_metadata:
    config:
      # Stage 1/5 — Filter specification
      filters:
        camera_id: camera01
        image_type: colorimage
      # Stage 2/5 — QueryComponent (DuckDB over L1–L4)
      metadata_file: s3://orx-metadata/metadata_4dor.csv
      limit: 10
  retrieve_objects:
    config:
      # Stage 4/5 + 5/5 — Object Retrieval + Local Filesystem Export
      dataset: 4dor-dataset
      filters:
        camera_id: camera01
        image_type: colorimage
      max_files: 5
      metadata_file: s3://orx-metadata/metadata_4dor.csv
```

### Stage 1/5 — Filter specification

`filters` is a free-form dict that becomes a DuckDB `WHERE` clause. Lists
become `IN (...)`; scalars become `=`.

### Stage 2/5 — `QueryComponent` (DuckDB) over L1–L4 — `query_metadata`

`query_metadata` calls `QueryComponent.query_metadata(...)` against the
`s3://orx-metadata/metadata_4dor.csv` path. DuckDB's `httpfs` extension
streams the CSV directly from MinIO.

### Stage 3/5 — Matched Metadata Records — `query_metadata`

The same asset emits `result_count`, `filters_applied`, and the resolved
`metadata_file` as Dagster metadata. Click the asset and open the
**Metadata** tab to see the count and the JSON preview of the filters.

### Stage 4/5 — Object Retrieval — `retrieve_objects`

`retrieve_objects` calls `ObjectRetrievalComponent.retrieve_objects(...)`,
which re-runs the query, resolves S3 object keys, and downloads each match
to the container's `/app/retrieved_data/`. The asset metadata reports
`total_files`, `successful_downloads`, `dataset`, and the filter dict.

### Stage 5/5 — Local Filesystem Export — `retrieve_objects`

Files land under `${RETRIEVED_DATA_PATH}` on the host (default
`./dataspaces/retrieved_data`). Verify with:

```bash
host$ ls dataspaces/retrieved_data/4dor-dataset/experiment-1/camera01/colorimage/
```

---

## Step 5 — Why two `execute_in_process` calls work

Workflow B's `query_metadata` declares
`AssetIn("generate_metadata")` — it cannot run unless the upstream asset
has been materialised. The example handles this transparently via three
small pieces of plumbing:

1. **Shared `DagsterInstance.ephemeral()`** — both `execute_in_process`
   calls receive the same instance, so its in-memory event log retains
   Workflow A's materialisation events when Workflow B starts.
2. **`FilesystemIOManager` bound at the `Definitions` level** — asset
   outputs are pickled under a tempdir (`DATORCLOUD_DAGSTER_IO_DIR` env
   var; defaults to `${TMP}/datorcloud_dagster_io`). The second run reads
   `generate_metadata`'s payload from there.
3. **Explicit `metadata_file` in Workflow B's run config** — the asset
   loads the upstream payload but the `s3://` path is also passed via
   config so the example is self-contained.

In the Dagster UI the same mechanism applies: materialise
`datorcloud_ingestion_job` first; the next time you launch
`datorcloud_query_fetch_job`, Dagster picks up the latest materialisation
of `generate_metadata` automatically.

---

## Step 6 — Customising the resource and storage paths

`DatorCloudResource` reads every connection field from `.env` via Pydantic
`default_factory`s, so the launchpad YAML only needs to override what you
actually want to change. The defaults applied by the example are:

```python
datorcloud_resource = DatorCloudResource(
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)
```

To pin extra fields (e.g. a different MinIO endpoint), add a `resources`
block to the launchpad YAML:

```yaml
resources:
  datorcloud:
    config:
      minio_endpoint: minio-staging:9090
      data_bucket: orx-datalake-stage
      metadata_bucket: orx-metadata-stage
ops:
  # ... per-asset config as above ...
```

To pin where the `FilesystemIOManager` stores pickled outputs (useful for
debugging cross-job state), export `DATORCLOUD_DAGSTER_IO_DIR` before
launching the example:

```bash
host$ docker exec -e DATORCLOUD_DAGSTER_IO_DIR=/app/dataspaces/.dagster_io \
        -it python-runner python /app/examples/datorcloud_dagster_workflow.py
```

---

## Troubleshooting

| Symptom                                                              | Cause / Fix                                                                                                                                              |
| :------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'dagster'` when running the script in `python-runner` | The container bootstrap did not include the `[dagster]` extra. With the current `docker-compose.yml` the install is `pip install -e '/app[dagster]'`; if the container started before that change, recreate it: `docker compose up -d --force-recreate python-runner`. |
| `AttributeError: 'UnresolvedAssetJobDefinition' object has no attribute 'execute_in_process'` | Dagster 1.11+ returns an *unresolved* job from `define_asset_job`. The example resolves it via `defs.get_job_def("datorcloud_ingestion_job")` (and the query/fetch counterpart) before calling `execute_in_process`. If you copy the example into your own script, do the same lookup through `Definitions`. |
| Launchpad shows `Missing required config entry 'dataset_paths' / 'dataset_dirs'` | The launchpad is empty because the job was defined without a default `config=`. Both bundled jobs ship pre-filled config via `define_asset_job(config=INGESTION_RUN_CONFIG / QUERY_FETCH_RUN_CONFIG)`; if the form is still empty, refresh the Dagster UI tab or restart the container with `docker compose restart dagster`. |
| Dagster UI shows a `src.dagster_quickstart` code location (status **Failed**) | The image's baked-in `start.sh` is loading a stale template. The current `docker-compose.yml` overrides it with `dagster dev -w /app/workspace/workspace.yaml`. Recreate the container: `docker compose up -d --force-recreate dagster` and reload the UI. |
| `query_metadata` asset fails with "upstream asset not materialized"  | Workflow A has not been run in this Dagster instance yet. Materialise `datorcloud_ingestion_job` first, or launch the script which runs both in order.   |
| `RuntimeError: Failed to load httpfs extension`                      | DuckDB extension cache is stale. `QueryComponent` already falls back to `FORCE INSTALL httpfs`; if it still fails, wipe the cache with `docker exec python-runner rm -rf /root/.duckdb/extensions`. |
| Empty Workflow B result                                              | The filter dict doesn't match any rows in the L2 metadata. Open `query_metadata`'s **Metadata** tab and check `result_count`; try a broader filter.      |
| Dagster UI shows only one job                                        | The webserver loaded a stale workspace. Restart with `docker compose restart dagster` or run `dagster dev -f /app/workspace/examples/datorcloud_dagster_workflow.py` manually. |
| Launchpad config rejected as invalid                                 | The YAML keys must match the `Config` class field names exactly (`dataset_paths`, `dataset_dirs`, `output_file`, `object_name`, `metadata_file`, `filters`, `limit`, `max_files`, `dataset`). |

---

## Next steps

- [Tutorial — 4dor-dataset](tutorial_4dor.md) — the same two workflows executed via the components / CLI directly.
- [Dagster Integration](dagster.md) — reference for `DatorCloudResource`, `Config` classes, and the asset chain.
- [Python API](python_api.md) — full component reference.
- [Architecture](../03_components/architecture.md) — how the L1–L4 data model maps onto the components.
