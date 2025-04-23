from dagster import asset, AssetIn, Output, MetadataValue
from typing import Dict, List, Any, Optional

from ..core.datorcloud_orchestrator import DatorCloudOrchestrator
from ..components.minio_component import MinioObjectComponent
from ..components.metadata_generator_component import MetadataGeneratorComponent
from ..components.metadata_storage_component import MetadataStorageComponent
from ..components.query_component import QueryComponent
from ..components.retrieval_component import ObjectRetrievalComponent


class DatorCloudComponents:
    """Container class holding DatorCloud components for Dagster assets."""
    
    def __init__(
        self,
        minio_endpoint: str = "minio:9090",
        minio_access_key: str = "minioadmin",
        minio_secret_key: str = "minioadmin",
        minio_secure: bool = False,
        s3_region: str = "us-east-1",
        data_bucket: str = "orx-datalake",
        metadata_bucket: str = "orx-metadata",
        local_data_dir: str = "./data",
        local_download_dir: str = "./retrieved_data"
    ):
        """
        Initialize DatorCloud components.
        
        Args:
            minio_endpoint: MinIO server endpoint
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
            minio_secure: Whether to use HTTPS for MinIO
            s3_region: S3 region for DuckDB
            data_bucket: Bucket for datasets
            metadata_bucket: Bucket for metadata
            local_data_dir: Local directory for data
            local_download_dir: Local directory for downloaded files
        """
        # Initialize components
        self.minio_component = MinioObjectComponent(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure
        )
        
        self.metadata_generator = MetadataGeneratorComponent()
        
        self.query_component = QueryComponent(
            s3_region=s3_region,
            s3_endpoint=minio_endpoint,
            s3_access_key=minio_access_key,
            s3_secret_key=minio_secret_key,
            s3_use_ssl=minio_secure
        )
        
        self.metadata_storage = MetadataStorageComponent(
            minio_component=self.minio_component,
            metadata_bucket=metadata_bucket
        )
        
        self.retrieval_component = ObjectRetrievalComponent(
            minio_component=self.minio_component,
            query_component=self.query_component,
            local_base_dir=local_download_dir
        )
        
        # Store configuration
        self.data_bucket = data_bucket
        self.metadata_bucket = metadata_bucket
        self.local_data_dir = local_data_dir
        self.local_download_dir = local_download_dir


@asset
def upload_datasets(
    components: DatorCloudComponents,
    dataset_paths: Dict[str, str],
    bucket_name: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Upload datasets to MinIO storage.
    
    Args:
        components: DatorCloud components container
        dataset_paths: Dictionary mapping dataset names to directory paths
        bucket_name: Optional bucket name override
        
    Returns:
        Dictionary with upload results
    """
    target_bucket = bucket_name or components.data_bucket
    components.minio_component.ensure_bucket_exists(target_bucket)
    
    results = {}
    for dataset_name, dataset_path in dataset_paths.items():
        results[dataset_name] = components.minio_component.upload_directory(
            local_directory=dataset_path,
            bucket_name=target_bucket,
            prefix=dataset_name
        )
    
    # Calculate metrics
    total_files = sum(len(files) for files in results.values())
    successful = sum(
        len([f for f in files if f.get("status") == "success"])
        for files in results.values()
    )
    
    # Return with metadata
    return Output(
        results,
        metadata={
            "total_files": total_files,
            "successful_uploads": successful,
            "datasets": len(dataset_paths)
        }
    )


@asset(
    ins={"upload_results": AssetIn("upload_datasets")}
)
def generate_metadata(
    components: DatorCloudComponents,
    upload_results: Dict[str, List[Dict[str, Any]]],
    dataset_dirs: Dict[str, str],
    output_file: str = "metadata.csv",
    bucket_name: Optional[str] = None,
    object_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate and upload metadata.
    
    Args:
        components: DatorCloud components container
        upload_results: Results from dataset upload
        dataset_dirs: Dictionary mapping dataset names to directory paths
        output_file: Local path to save metadata CSV
        bucket_name: Optional bucket name override
        object_name: Optional object name override
        
    Returns:
        Dictionary with metadata information
    """
    metadata_df = components.metadata_storage.create_metadata_and_store(
        metadata_generator_component=components.metadata_generator,
        dataset_dirs=dataset_dirs,
        local_file_path=output_file,
        bucket_name=bucket_name,
        object_name=object_name
    )
    
    # Return with metadata
    return Output(
        {
            "record_count": len(metadata_df),
            "datasets": list(dataset_dirs.keys()),
            "columns": list(metadata_df.columns),
            "output_file": output_file
        },
        metadata={
            "record_count": len(metadata_df),
            "datasets": MetadataValue.json(list(dataset_dirs.keys())),
            "columns": MetadataValue.json(list(metadata_df.columns))
        }
    )


@asset(
    ins={"metadata_info": AssetIn("generate_metadata")}
)
def query_metadata(
    components: DatorCloudComponents,
    metadata_info: Dict[str, Any],
    filters: Dict[str, Any],
    limit: Optional[int] = None,
    metadata_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query metadata from the metadata store.
    
    Args:
        components: DatorCloud components container
        metadata_info: Information about the metadata
        filters: Dictionary of column:value filters
        limit: Maximum number of results
        metadata_file: Optional S3 path to metadata file
        
    Returns:
        Dictionary with query results
    """
    # If metadata_file not provided, use default
    if metadata_file is None:
        metadata_file = f"s3://{components.metadata_bucket}/metadata.csv"
    
    results_df = components.query_component.query_metadata(
        metadata_file=metadata_file,
        filters=filters,
        limit=limit
    )
    
    # Return with metadata
    return Output(
        {
            "result_count": len(results_df),
            "filters": filters,
            "results": results_df.to_dict(orient="records")
        },
        metadata={
            "result_count": len(results_df),
            "filters_applied": MetadataValue.json(filters)
        }
    )


@asset(
    ins={"query_results": AssetIn("query_metadata")}
)
def retrieve_objects(
    components: DatorCloudComponents,
    query_results: Dict[str, Any],
    dataset: str,
    metadata_file: Optional[str] = None,
    max_files: Optional[int] = None,
    **filters
) -> List[Dict[str, Any]]:
    """
    Retrieve objects based on metadata query.
    
    Args:
        components: DatorCloud components container
        query_results: Results from metadata query
        dataset: Dataset name
        metadata_file: Optional S3 path to metadata file
        max_files: Maximum number of files to retrieve
        **filters: Additional filter criteria
        
    Returns:
        List of dictionaries with information about retrieved files
    """
    # If metadata_file not provided, use default
    if metadata_file is None:
        metadata_file = f"s3://{components.metadata_bucket}/metadata.csv"
        
    downloaded_files = components.retrieval_component.retrieve_objects(
        metadata_file=metadata_file,
        dataset=dataset,
        data_bucket=components.data_bucket,
        max_files=max_files,
        **filters
    )
    
    # Calculate metrics
    successful = sum(1 for f in downloaded_files if f.get("success", False))
    
    # Return with metadata
    return Output(
        downloaded_files,
        metadata={
            "total_files": len(downloaded_files),
            "successful_downloads": successful,
            "dataset": dataset,
            "filters": MetadataValue.json(filters)
        }
    )


# Collection of assets for a complete DatorCloud workflow
component_assets = [
    upload_datasets,
    generate_metadata,
    query_metadata,
    retrieve_objects
] 
