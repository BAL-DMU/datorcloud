# Architecture

The **DatorCloud framework** implements a **four-layer data model (L1–L4)**
over **three storage tiers**, exposed as **five single-responsibility
components** and one orchestrator. The framework is built on **DuckDB** and
**MinIO** and integrates with **JupyterHub / BAL-JH Spaces** for
collaborative research. A Dagster orchestration layer is optional.

![DatorCloud architecture](datorcloud_architecture.png)

*Fig. 1 — DatorCloud architecture overview.*

## Data model (L1–L4)

| Layer | Name                 | Content                                  |
| :---- | :------------------- | :--------------------------------------- |
| L1    | Experiment Card      | ID, location, date, anatomy, privacy.    |
| L2    | Sensor Metadata      | Sensor, modality, timestamps.            |
| L3    | Semantic Annotations | Phases, tools, labels.                   |
| L4    | Dataset Composition  | Queries across L2/L3.                    |

## Software architecture

Five components live under `datorcloud/components/`. The orchestrator
(`datorcloud.core.DatorCloudOrchestrator`) wires them together; its
`from_env()` classmethod loads `.env` and constructs the full pipeline
without exposing any credentials in user code.

| Component                       | Responsibility                       |
| :------------------------------ | :----------------------------------- |
| `MinioObjectComponent`          | Object storage interface.            |
| `MetadataGeneratorComponent`    | L2 metadata extraction.              |
| `MetadataStorageComponent`      | L1–L3 metadata persistence.          |
| `QueryComponent`                | DuckDB queries over L1–L4.           |
| `ObjectRetrievalComponent`      | Fetch matched objects.               |

## Storage tiers

| Tier                 | Engine               | Holds                                                        |
| :------------------- | :------------------- | :----------------------------------------------------------- |
| Database Catalog     | DuckDB               | L1 — Experiment Card Table, Dataset Card Table.              |
| NoSQL Metadata Store | MinIO + DuckDB JSON  | L2/L3 per experiment; L4 dataset cards.                      |
| Object Store         | MinIO                | Raw multimodal data: color, depth, point clouds, sensor info. |

## Operational workflows

**A. Ingestion**

```
device / sensor data → Object Store (MinIO) → Metadata Generation
                    → NoSQL Metadata Store  → Database Catalog update
```

**B. Query & Fetch**

```
filter specification → QueryComponent (DuckDB) → Matched Metadata Records
                    → Object Retrieval         → Local Filesystem Export
```

## Optional workflow layer (Dagster)

`datorcloud.dagster.DatorCloudResource` (a `ConfigurableResource`) exposes
four chained assets:

```
upload_datasets → generate_metadata → query_metadata → retrieve_objects
```

The repository-level `workspace.yaml` loads `examples/dagster_workflow.py`,
so `dagster dev` is enough to materialize the full pipeline.

## Key technologies

DuckDB · MinIO · Python · Dagster (optional)

## Deployment environment

- **Trusted Research Environment (TRE)** — institutional secure research
  compute and storage platform.
- **BAL-JH Spaces** — JupyterHub research environment integrated with the
  TRE.

## See also

- [Quickstart](../04_user_guide/quickstart.md)
- [Python API](../04_user_guide/python_api.md)
- [Dagster Integration](../04_user_guide/dagster.md)
- [Contributing](../05_contributing/contributing.md)
