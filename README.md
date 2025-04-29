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

```bash
pip install datorcloud
```

## Features

- MinIO object storage integration
- Metadata generation and management
- Dagster assets for data workflows
- Dataset upload and retrieval

## Usage

### Basic Usage

```python
from datorcloud import MinioObjectComponent, MetadataGeneratorComponent

# Initialize MinIO component
minio_component = MinioObjectComponent(
    endpoint="minio:9090",
    bucket_name="orx-datalake"
)

# Upload a dataset
minio_component.upload_directory(
    directory_path="./data/my-dataset",
    object_prefix="my-dataset/"
)

# Generate metadata
metadata_component = MetadataGeneratorComponent(
    output_file="./metadata.csv",
    minio_component=minio_component
)

metadata_component.generate_metadata(
    dataset_dirs={"my-dataset": "./data/my-dataset"}
)
```

### Dagster Integration

DatorCloud provides Dagster assets for creating data workflows:

```python
from dagster import Definitions, define_asset_job, AssetSelection
from datorcloud.dagster import (
    DatorCloudComponents,
    component_assets
)

# Initialize components
dator_components = DatorCloudComponents(
    minio_endpoint="minio:9090",
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
    local_data_dir="./data",
    local_download_dir="./retrieved_data"
)

# Create a job
datorcloud_job = define_asset_job(
    name="datorcloud_workflow_job",
    selection=AssetSelection.assets(*component_assets)
)

# Define Dagster definitions
defs = Definitions(
    assets=component_assets,
    jobs=[datorcloud_job],
    resources={
        "components": dator_components
    }
)
```

See the `examples` directory for complete workflow examples.

## Example Workflow

The package includes predefined Dagster assets for common operations:

1. `upload_datasets` - Upload datasets to MinIO
2. `generate_metadata` - Generate metadata for uploaded datasets
3. `query_metadata` - Query the metadata based on filters
4. `retrieve_objects` - Download objects based on metadata queries

## License

MIT

