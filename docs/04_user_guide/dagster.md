# Dagster Integration

The **DatorCloud framework** ships ready-to-use Dagster assets so the same
pipeline you call from Python or the CLI can also run as a graph in the
Dagster UI.

> **Looking for a step-by-step walkthrough?** See
> [Tutorial — Dagster Workflows](tutorial_dagster.md), which materialises
> Workflow A (Ingestion) and Workflow B (Query & Fetch) as two separate
> jobs in the Dagster UI.

## What you get

`datorcloud.dagster` exposes:

| Symbol                                                            | Purpose                                                                  |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `DatorCloudResource`                                              | A `ConfigurableResource` that builds all components from a single config. |
| `UploadDatasetsConfig`, `GenerateMetadataConfig`,                 | One `dagster.Config` per asset (Pydantic-based, fully typed).            |
| `QueryMetadataConfig`, `RetrieveObjectsConfig`                    |                                                                          |
| `upload_datasets`, `generate_metadata`, `query_metadata`,         | Four chained `@asset`s.                                                  |
| `retrieve_objects`                                                |                                                                          |
| `component_assets`                                                | The four assets bundled as a list.                                       |

## Run the bundled workflow

The repository root contains a `workspace.yaml` pointing at
`examples/datorcloud_dagster_workflow.py`, which already wires the resource, the assets,
and a `datorcloud_workflow_job`:

```bash
pip install -e ".[dagster]"
dagster dev
```

Open <http://127.0.0.1:3030>, select **datorcloud_workflow_job**, and
materialize the assets. (The bundled `dagster` container in `docker-compose.yml`
also runs on port **3030**.)

## Wire it into your own `Definitions`

`DatorCloudResource` uses Pydantic `default_factory` to read every connection
and storage field from the project `.env` (`S3_ENDPOINT`, `S3_ACCESS_KEY`,
`S3_SECRET_KEY`, `S3_USE_SSL`, `S3_REGION`, `DATA_LAKE_PATH`,
`RETRIEVED_DATA_PATH`, `DUCKDB_HTTPFS_EXTENSION_PATH`). Construct the resource
with no arguments to pick up everything from the environment, or pass keyword
overrides for any field you want to pin in code or in `run_config`.

```python
from dagster import Definitions, define_asset_job, AssetSelection
from datorcloud.dagster import DatorCloudResource, component_assets

resource = DatorCloudResource(
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)

job = define_asset_job(
    name="datorcloud_workflow_job",
    selection=AssetSelection.assets(*component_assets),
)

defs = Definitions(
    assets=component_assets,
    jobs=[job],
    resources={"datorcloud": resource},
)
```

## Configuring a run

Each asset reads its parameters from a `Config` class, so values are supplied
via `run_config`:

```python
run_config = {
    "ops": {
        "upload_datasets": {
            "config": {
                "dataset_paths": {"4dor-dataset": "./dataspaces/data_lake/4dor-dataset"},
            }
        },
        "generate_metadata": {
            "config": {
                "dataset_dirs": {"4dor-dataset": "./dataspaces/data_lake/4dor-dataset"},
                "output_file": "./dataspaces/data_lake/metadata.csv",
                "object_name": "metadata.csv",
            }
        },
        "query_metadata": {
            "config": {"filters": {"camera_id": "camera01"}, "limit": 10}
        },
        "retrieve_objects": {
            "config": {
                "dataset": "4dor-dataset",
                "filters": {"camera_id": "camera01"},
                "max_files": 5,
            }
        },
    }
}
```

In the Dagster UI the **Launchpad** offers a typed form for the same fields.

## Notes

- The four assets form a strict dependency chain:
  `upload_datasets → generate_metadata → query_metadata → retrieve_objects`.
- `DatorCloudResource` rebuilds components on every property access; do **not**
  store state on the instance, it does not survive a materialization.
- Component construction is cheap (no I/O at init), so this is safe.
