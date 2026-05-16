# `src/orx-surghub/` — Legacy scripts (DEPRECATED)

The standalone scripts in this folder predate the refactor into the
`datorcloud` Python package. They are kept for reference only and **should not
be used for new code**.

All functionality has been moved into the modular component package under
[`datorcloud/`](../../datorcloud/) and is exposed through:

| Legacy script                          | New component / orchestrator entry point                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------- |
| `metadata-generator.py`                | `datorcloud.MetadataGeneratorComponent` and `DatorCloudOrchestrator.generate_and_upload_metadata` |
| `upload_object_to_minio.py`            | `datorcloud.MinioObjectComponent.upload_directory` / `DatorCloudOrchestrator.upload_datasets` |
| `upload_metadata_to_minio.py`          | `datorcloud.MetadataStorageComponent.store_metadata`                                  |
| `retrieval_object_data.py`             | `datorcloud.ObjectRetrievalComponent.retrieve_objects` / `DatorCloudOrchestrator.retrieve_data` |
| `query_metadata_duckdb.py`             | `datorcloud.QueryComponent.query_metadata` / `DatorCloudOrchestrator.query_metadata`  |
| `duckdb_database_creation.py`          | `datorcloud.QueryComponent` (handles `httpfs` + S3 configuration at construction)     |

Preferred replacements:

- For Python code: `from datorcloud import ...`
- For shell automation: the `datorcloud` CLI (see `datorcloud --help`)
- For pipelines: the Dagster assets in `datorcloud.dagster`

These legacy scripts will be removed in a future release once all downstream
notebooks and pipelines have migrated.
