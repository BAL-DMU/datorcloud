# DatorCloud - Multimodal Data Management and Sharing Platform

**DatorCloud** is a lightweight, self-hosted cloud platform developed at Balgrist University Hospital and the OR-X Translational Center for Surgery. It simplifies the management, querying, and sharing of multimodal research data—including images, videos, sensor data, and clinical records—using **DuckDB** for fast, SQL-like analytics and **MinIO** for S3-compatible object storage.

Designed for research teams and institutions, DatorCloud offers a modular and scalable solution for organizing and exploring complex datasets without requiring heavy infrastructure.

### Key Features
- **Multimodal Data Management**: Organize and access diverse datasets in a structured, web-based environment.
- **Unified Dataset Catalog**: Browse and manage datasets by project, researcher, or experimental context.
- **Custom Dataset Composition**: Create tailored datasets using SQL-like queries over object storage.
- **Efficient, Traceable Access**: Query large datasets directly with DuckDB and MinIO CLIs, reducing duplication and enabling reproducible analysis.


## DatorCloud Component

A Python package for managing data and metadata with MinIO integration and Dagster workflow support.

## Installation

From source (recommended during development):

```bash
pip install -e .[dagster,test]
```

## Features

- MinIO object storage integration
- Metadata generation and management
- DuckDB-backed SQL queries over object storage
- Dagster assets and resources for data workflows
- Dataset upload and retrieval

## Usage

### Basic Usage

Credentials must come from the project `.env` (loaded via `python-dotenv`),
never hard-coded. Each component validates that real values were supplied.

```python
import os
from dotenv import load_dotenv

from datorcloud import (
    MinioObjectComponent,
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    QueryComponent,
    ObjectRetrievalComponent,
)

load_dotenv()

minio = MinioObjectComponent(
    endpoint=os.environ.get("S3_ENDPOINT", "minio:9090"),
    access_key=os.environ["S3_ACCESS_KEY"],
    secret_key=os.environ["S3_SECRET_KEY"],
)

# Upload a dataset directory (DATA_LAKE_PATH from .env defaults to ./dataspaces/data_lake)
minio.upload_directory(
    local_directory="./dataspaces/data_lake/my-dataset",
    bucket_name="orx-datalake",
    prefix="my-dataset",
)

# Generate metadata
generator = MetadataGeneratorComponent()
storage = MetadataStorageComponent(minio_component=minio, metadata_bucket="orx-metadata")

metadata_df = storage.create_metadata_and_store(
    metadata_generator_component=generator,
    dataset_dirs={"my-dataset": "./dataspaces/data_lake/my-dataset"},
    local_file_path="./dataspaces/data_lake/metadata.csv",
    object_name="metadata.csv",
)
```

### Orchestrated Usage

The orchestrator ships a `from_env()` factory that wires every component
from the project `.env` — no credentials are hard-coded.

```python
from datorcloud.core import DatorCloudOrchestrator

orchestrator = DatorCloudOrchestrator.from_env(
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)

orchestrator.upload_datasets({"my-dataset": "./dataspaces/data_lake/my-dataset"})
orchestrator.generate_and_upload_metadata(
    dataset_dirs={"my-dataset": "./dataspaces/data_lake/my-dataset"},
    output_file="./dataspaces/data_lake/metadata.csv",
    object_name="metadata.csv",
)

results = orchestrator.query_metadata(filters={"camera_id": "camera01"}, limit=10)
```

### Dagster Integration

DatorCloud provides a typed `DatorCloudResource` and four assets you can wire into a `Definitions` object:

```python
from dagster import Definitions, define_asset_job, AssetSelection
from datorcloud.dagster import (
    DatorCloudResource,
    component_assets,
)

resource = DatorCloudResource(
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)
# Every other field (endpoint, credentials, paths) is pulled from .env via
# Pydantic ``default_factory``; pass an explicit value to override any of them.

datorcloud_job = define_asset_job(
    name="datorcloud_workflow_job",
    selection=AssetSelection.assets(*component_assets),
)

defs = Definitions(
    assets=component_assets,
    jobs=[datorcloud_job],
    resources={"datorcloud": resource},
)
```

See `examples/` for complete workflows.

## Example Workflow

The package includes predefined Dagster assets for common operations:

1. `upload_datasets` - Upload datasets to MinIO
2. `generate_metadata` - Generate metadata for uploaded datasets
3. `query_metadata` - Query the metadata based on filters
4. `retrieve_objects` - Download objects based on metadata queries

## Testing

```bash
pip install -e .[test]
pytest -q
```

## License

MIT

