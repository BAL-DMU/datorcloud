from typing import Dict, List, Optional, Any
import pandas as pd
import os

from ..services.minio_service import MinioObjectService
from ..services.metadata_service import MetadataService
from ..services.query_service import QueryService
from ..services.retrieval_service import RetrievalService


class DatorCloud:
    """
    Main coordinator class for DatorCloud operations.
    Orchestrates the workflow between different services.
    """
    
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
        Initialize DatorCloud with configuration parameters.
        
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
        # Initialize MinIO service
        self.minio_service = MinioObjectService(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure
        )
        
        # Initialize metadata service
        self.metadata_service = MetadataService()
        
        # Initialize query service
        self.query_service = QueryService(
            s3_region=s3_region,
            s3_endpoint=minio_endpoint,
            s3_access_key=minio_access_key,
            s3_secret_key=minio_secret_key,
            s3_use_ssl=minio_secure
        )
        
        # Initialize retrieval service
        self.retrieval_service = RetrievalService(
            minio_service=self.minio_service,
            query_service=self.query_service,
            local_base_dir=local_download_dir
        )
        
        # Store configuration
        self.data_bucket = data_bucket
        self.metadata_bucket = metadata_bucket
        self.local_data_dir = local_data_dir
        self.local_download_dir = local_download_dir
    
    def upload_datasets(
        self, 
        dataset_paths: Dict[str, str], 
        bucket_name: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Upload datasets to MinIO.
        
        Args:
            dataset_paths: Dictionary mapping dataset names to directory paths
            bucket_name: Optional bucket name override
            
        Returns:
            Dictionary with results for each dataset
        """
        target_bucket = bucket_name or self.data_bucket
        self.minio_service.ensure_bucket_exists(target_bucket)
        
        results = {}
        
        for dataset_name, dataset_path in dataset_paths.items():
            if os.path.exists(dataset_path):
                results[dataset_name] = self.minio_service.upload_directory(
                    local_directory=dataset_path,
                    bucket_name=target_bucket,
                    prefix=dataset_name
                )
            else:
                print(f"Dataset path '{dataset_path}' does not exist.")
                results[dataset_name] = []
        
        return results
    
    def generate_and_upload_metadata(
        self,
        dataset_dirs: Dict[str, str],
        output_file: str = "metadata.csv",
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Generate metadata for datasets and upload to MinIO.
        
        Args:
            dataset_dirs: Dictionary mapping dataset names to directory paths
            output_file: Local path to save metadata CSV
            bucket_name: Optional bucket name override
            object_name: Optional object name override
            
        Returns:
            DataFrame containing the generated metadata
        """
        # Generate metadata
        metadata_df = self.metadata_service.generate_metadata(
            dataset_dirs=dataset_dirs,
            output_file=output_file
        )
        
        # Upload metadata to MinIO
        target_bucket = bucket_name or self.metadata_bucket
        target_object = object_name or os.path.basename(output_file)
        
        self.minio_service.ensure_bucket_exists(target_bucket)
        self.minio_service.upload_file(
            bucket_name=target_bucket,
            object_name=target_object,
            file_path=output_file
        )
        
        return metadata_df
    
    def query_metadata(
        self,
        metadata_file: Optional[str] = None,
        filters: Dict[str, Any] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Query metadata from the metadata store.
        
        Args:
            metadata_file: S3 path to metadata file (default: 's3://{bucket}/metadata.csv')
            filters: Dictionary of column:value filters
            limit: Maximum number of results
            
        Returns:
            DataFrame with query results
        """
        if metadata_file is None:
            metadata_file = f"s3://{self.metadata_bucket}/metadata.csv"
        
        return self.query_service.query_metadata(
            metadata_file=metadata_file,
            filters=filters,
            limit=limit
        )
    
    def retrieve_data(
        self,
        dataset: str,
        metadata_file: Optional[str] = None,
        max_files: Optional[int] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Retrieve data based on metadata query.
        
        Args:
            dataset: Dataset name
            metadata_file: S3 path to metadata file (default: 's3://{bucket}/metadata.csv')
            max_files: Maximum number of files to retrieve
            **filters: Additional filter criteria
            
        Returns:
            List of dictionaries with information about retrieved files
        """
        if metadata_file is None:
            metadata_file = f"s3://{self.metadata_bucket}/metadata.csv"
        
        return self.retrieval_service.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=self.data_bucket,
            max_files=max_files,
            **filters
        )
    
    def retrieve_experiment(
        self,
        dataset: str,
        experiment: str,
        metadata_file: Optional[str] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Retrieve data for a specific experiment.
        
        Args:
            dataset: Dataset name
            experiment: Experiment name
            metadata_file: S3 path to metadata file (default: 's3://{bucket}/metadata.csv')
            **filters: Additional filter criteria
            
        Returns:
            List of dictionaries with information about retrieved files
        """
        if metadata_file is None:
            metadata_file = f"s3://{self.metadata_bucket}/metadata.csv"
        
        return self.retrieval_service.retrieve_experiment_data(
            metadata_file=metadata_file,
            dataset=dataset,
            experiment=experiment,
            data_bucket=self.data_bucket,
            **filters
        ) 
