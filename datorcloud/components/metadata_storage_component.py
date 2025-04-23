import os
from typing import Dict, List, Optional, Any
import pandas as pd

from .minio_component import MinioObjectComponent


class MetadataStorageComponent:
    """Component for managing metadata storage in MinIO."""
    
    def __init__(
        self,
        minio_component: MinioObjectComponent,
        metadata_bucket: str = "orx-metadata"
    ):
        """
        Initialize the metadata storage component.
        
        Args:
            minio_component: MinIO component for object storage operations
            metadata_bucket: Default bucket for metadata storage
        """
        self.minio_component = minio_component
        self.metadata_bucket = metadata_bucket
    
    def store_metadata(
        self, 
        metadata_df: pd.DataFrame,
        local_file_path: str,
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None
    ) -> bool:
        """
        Store metadata in MinIO.
        
        Args:
            metadata_df: DataFrame containing metadata
            local_file_path: Path to save local copy
            bucket_name: Optional bucket name override
            object_name: Optional object name in MinIO
            
        Returns:
            True if successful, False otherwise
        """
        target_bucket = bucket_name or self.metadata_bucket
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
        
        # Save metadata locally
        try:
            metadata_df.to_csv(local_file_path, index=False)
        except Exception as e:
            print(f"Error saving metadata to local file {local_file_path}: {e}")
            return False
            
        # Determine object name
        target_object = object_name or os.path.basename(local_file_path)
        
        # Upload to MinIO
        return self.minio_component.upload_file(
            bucket_name=target_bucket,
            object_name=target_object,
            file_path=local_file_path
        )
    
    def create_metadata_and_store(
        self,
        metadata_generator_component,
        dataset_dirs: Dict[str, str],
        local_file_path: str,
        bucket_name: Optional[str] = None,
        object_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Generate metadata and store it in MinIO.
        
        Args:
            metadata_generator_component: Component for generating metadata
            dataset_dirs: Dictionary mapping dataset names to directory paths
            local_file_path: Path to save local copy
            bucket_name: Optional bucket name override
            object_name: Optional object name in MinIO
            
        Returns:
            DataFrame containing the generated metadata
        """
        # Generate metadata
        metadata_df = metadata_generator_component.generate_metadata(
            dataset_dirs=dataset_dirs,
            output_file=local_file_path
        )
        
        # Store in MinIO
        success = self.store_metadata(
            metadata_df=metadata_df,
            local_file_path=local_file_path,
            bucket_name=bucket_name,
            object_name=object_name
        )
        
        if not success:
            print("Warning: Metadata was generated but could not be stored in MinIO.")
        
        return metadata_df 
