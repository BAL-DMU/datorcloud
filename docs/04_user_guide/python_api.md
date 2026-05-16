# Python API

The **DatorCloud framework** can be used at two levels: the **orchestrator**
(one object, full pipeline) or the **individual components** (compose your
own workflow).

## Orchestrator

```python
from datorcloud.core import DatorCloudOrchestrator

orch = DatorCloudOrchestrator(
    minio_endpoint="minio:9090",
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)

orch.upload_datasets({"4dor-dataset": "./data/4dor-dataset"})

orch.generate_and_upload_metadata(
    dataset_dirs={"4dor-dataset": "./data/4dor-dataset"},
    output_file="./data/metadata.csv",
    object_name="metadata.csv",
)

df = orch.query_metadata(filters={"camera_id": "camera01"}, limit=10)

files = orch.retrieve_data(
    dataset="4dor-dataset",
    camera_id="camera01",
    max_files=5,
)
```

You can inject custom components into the constructor — useful for tests or
alternate backends:

```python
orch = DatorCloudOrchestrator(
    minio_component=my_minio,
    query_component=my_query,
)
```

## Individual components

```python
from datorcloud import (
    MinioObjectComponent,
    MetadataGeneratorComponent,
    MetadataStorageComponent,
    QueryComponent,
    ObjectRetrievalComponent,
)

minio = MinioObjectComponent(endpoint="minio:9090")
minio.upload_directory("./data/4dor-dataset", "orx-datalake", prefix="4dor-dataset")

generator = MetadataGeneratorComponent()
storage = MetadataStorageComponent(minio_component=minio, metadata_bucket="orx-metadata")
df = storage.create_metadata_and_store(
    metadata_generator_component=generator,
    dataset_dirs={"4dor-dataset": "./data/4dor-dataset"},
    local_file_path="./data/metadata.csv",
    object_name="metadata.csv",
)

query = QueryComponent(s3_endpoint="minio:9090")
retrieval = ObjectRetrievalComponent(minio_component=minio, query_component=query)

results = query.query_metadata(
    metadata_file="s3://orx-metadata/metadata.csv",
    filters={"camera_id": "camera01"},
    limit=10,
)

downloaded = retrieval.retrieve_objects(
    metadata_file="s3://orx-metadata/metadata.csv",
    dataset="4dor-dataset",
    data_bucket="orx-datalake",
    camera_id="camera01",
    max_files=5,
)
```

## Cheat sheet

| Goal                                 | Component / method                                                    |
| ------------------------------------ | --------------------------------------------------------------------- |
| Create or check a bucket             | `MinioObjectComponent.ensure_bucket_exists`                           |
| Upload one file                      | `MinioObjectComponent.upload_file`                                    |
| Upload a directory tree              | `MinioObjectComponent.upload_directory`                               |
| Download one file                    | `MinioObjectComponent.download_file`                                  |
| Build a metadata DataFrame from disk | `MetadataGeneratorComponent.generate_metadata`                        |
| Write metadata locally + to MinIO    | `MetadataStorageComponent.create_metadata_and_store`                  |
| Query a metadata CSV with filters    | `QueryComponent.query_metadata`                                       |
| List S3 object keys for a query      | `QueryComponent.get_object_paths`                                     |
| Download all matching objects        | `ObjectRetrievalComponent.retrieve_objects`                           |
| Run the full pipeline                | `DatorCloudOrchestrator.upload_datasets` → `retrieve_data`            |

## Logging

All components use the standard `logging` module under the `datorcloud.*`
namespace. Enable it from your script:

```python
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
```
