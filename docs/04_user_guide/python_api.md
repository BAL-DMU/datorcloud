# Python API

The **DatorCloud framework** can be used at two levels: the **orchestrator**
(one object, full pipeline) or the **individual components** (compose your
own workflow).

## Orchestrator

`DatorCloudOrchestrator.from_env()` is the recommended entry point: it reads
every connection and storage value from the project `.env` and raises a clear
error if a required credential is missing.

```python
import os
from datorcloud.core import DatorCloudOrchestrator

# from_env() internally calls load_dotenv() and reads S3_ENDPOINT,
# S3_ACCESS_KEY, S3_SECRET_KEY, DATA_LAKE_PATH, RETRIEVED_DATA_PATH, ...
orch = DatorCloudOrchestrator.from_env(
    data_bucket="orx-datalake",
    metadata_bucket="orx-metadata",
)

DATA_LAKE = os.environ.get("DATA_LAKE_PATH", "./data_lake")

orch.upload_datasets({"4dor-dataset": f"{DATA_LAKE}/4dor-dataset"})

orch.generate_and_upload_metadata(
    dataset_dirs={"4dor-dataset": f"{DATA_LAKE}/4dor-dataset"},
    output_file=f"{DATA_LAKE}/metadata.csv",
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

Credentials are required arguments — no `"minioadmin"` fallbacks live in the
library code. Load `.env` once and forward the values into each component.

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
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "minio:9090")
S3_ACCESS_KEY = os.environ["S3_ACCESS_KEY"]
S3_SECRET_KEY = os.environ["S3_SECRET_KEY"]

minio = MinioObjectComponent(
    endpoint=S3_ENDPOINT,
    access_key=S3_ACCESS_KEY,
    secret_key=S3_SECRET_KEY,
)
minio.upload_directory(f"{DATA_LAKE}/4dor-dataset", "orx-datalake", prefix="4dor-dataset")

generator = MetadataGeneratorComponent()
storage = MetadataStorageComponent(minio_component=minio, metadata_bucket="orx-metadata")
df = storage.create_metadata_and_store(
    metadata_generator_component=generator,
    dataset_dirs={"4dor-dataset": f"{DATA_LAKE}/4dor-dataset"},
    local_file_path=f"{DATA_LAKE}/metadata.csv",
    object_name="metadata.csv",
)

query = QueryComponent(
    s3_endpoint=S3_ENDPOINT,
    s3_access_key=S3_ACCESS_KEY,
    s3_secret_key=S3_SECRET_KEY,
)
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
