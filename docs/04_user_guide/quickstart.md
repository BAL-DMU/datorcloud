# Quickstart

This page takes you from a fresh clone of the **DatorCloud framework** to a
working end-to-end pipeline in about five minutes. The framework can be used
locally, inside the project's Docker Compose stack, or from a
**BAL-JH Spaces** JupyterHub workspace.

## 1. Requirements

- Python ≥ 3.10
- Docker + Docker Compose (for MinIO + DuckDB services)
- Git

## 2. Clone and install

```bash
git clone https://github.com/jagh/datorcloud.git
cd datorcloud
pip install -e ".[dagster,test]"
```

`pip install -e .` installs the `datorcloud` Python package **and** the
`datorcloud` CLI in editable mode.

## 3. Start MinIO + DuckDB

The repo ships a `docker-compose.yml` and a sample `.env`:

```bash
cp .env.example .env       # then edit S3_ACCESS_KEY / S3_SECRET_KEY
docker compose up -d
```

DatorCloud reads every credential and storage path from this `.env` — the
components themselves no longer ship default credentials. Open the MinIO
console at <http://localhost:9091> and log in with whatever values you put
into `S3_ACCESS_KEY` / `S3_SECRET_KEY` (the template ships
`minioadmin` / `minioadmin` as a development default).

## 4. Run the pipeline

All project storage lives under `PROJECT_ROOT` (default `./dataspaces`).
Place a dataset under `${DATA_LAKE_PATH}/<dataset-name>/<experiment>/...`,
then:

```bash
# 1. Upload the directory tree to MinIO
datorcloud upload --dataset 4dor-dataset=./dataspaces/data_lake/4dor-dataset

# 2. Generate metadata and upload the CSV
datorcloud metadata --dataset 4dor-dataset=./dataspaces/data_lake/4dor-dataset \
                    --object-name metadata.csv

# 3. Query the metadata
datorcloud query --filter camera_id=camera01 --limit 10

# 4. Retrieve files matching the query
datorcloud retrieve --dataset 4dor-dataset \
                    --filter camera_id=camera01 --max-files 5
```

The four steps map 1:1 to the four
[Dagster assets](dagster.md) and to four methods on
[`DatorCloudOrchestrator`](python_api.md#orchestrator).

## 5. Run the test suite

```bash
pytest -q
```

You should see `30 passed`. The Dagster materialization test is auto-skipped
when Dagster is not installed.

## Next steps

- [Tutorial — 4dor-dataset](tutorial_4dor.md) — concrete walkthrough using the bundled multi-camera dataset.
- [Python API](python_api.md) — embed DatorCloud in a script or notebook.
- [CLI reference](cli.md) — full flag listing.
- [Dagster integration](dagster.md) — assets, resources, and `dagster dev`.
- [Component Architecture](../03_components/architecture.md) — how the pieces fit together.
