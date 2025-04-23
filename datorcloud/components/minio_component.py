import os
from typing import Dict, List, Optional
from minio import Minio
from minio.error import S3Error


class MinioObjectComponent:
    """Component for managing object storage operations with MinIO."""

    def __init__(
        self,
        endpoint: str = "minio:9090",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool = False
    ):
        """
        Initialize MinIO client connection.
        
        Args:
            endpoint: MinIO server endpoint
            access_key: MinIO access key
            secret_key: MinIO secret key
            secure: Whether to use HTTPS
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
    
    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """
        Create a bucket if it doesn't exist.
        
        Args:
            bucket_name: Name of the bucket to create or check
            
        Returns:
            bool: True if bucket exists or was created, False on failure
        """
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                return True
            return True
        except S3Error as err:
            print(f"Error ensuring bucket {bucket_name} exists: {err}")
            return False
    
    def upload_file(self, bucket_name: str, object_name: str, file_path: str) -> bool:
        """
        Upload a single file to MinIO.
        
        Args:
            bucket_name: Target bucket name
            object_name: Object name in MinIO
            file_path: Path to local file
            
        Returns:
            bool: True if upload successful, False otherwise
        """
        try:
            self.ensure_bucket_exists(bucket_name)
            self.client.fput_object(bucket_name, object_name, file_path)
            return True
        except S3Error as e:
            print(f"Error uploading file {file_path}: {e}")
            return False
    
    def upload_directory(
        self, 
        local_directory: str, 
        bucket_name: str, 
        prefix: str = ""
    ) -> List[Dict[str, str]]:
        """
        Recursively upload files from a local directory to MinIO.
        
        Args:
            local_directory: Path to local directory
            bucket_name: Target bucket name
            prefix: Prefix for object names
            
        Returns:
            List of dicts with info about uploaded files
        """
        uploaded_files = []
        
        self.ensure_bucket_exists(bucket_name)
        
        for root, _, files in os.walk(local_directory):
            for file in files:
                local_path = os.path.join(root, file)
                
                # Create object name with proper prefix
                relative_path = os.path.relpath(local_path, local_directory)
                object_name = os.path.join(prefix, relative_path).replace("\\", "/")
                
                try:
                    self.client.fput_object(bucket_name, object_name, local_path)
                    uploaded_files.append({
                        "local_path": local_path,
                        "bucket": bucket_name,
                        "object_name": object_name,
                        "status": "success"
                    })
                except S3Error as e:
                    uploaded_files.append({
                        "local_path": local_path,
                        "bucket": bucket_name,
                        "object_name": object_name,
                        "status": "error",
                        "error": str(e)
                    })
        
        return uploaded_files
    
    def download_file(
        self, 
        bucket_name: str, 
        object_name: str, 
        file_path: str
    ) -> bool:
        """
        Download a file from MinIO.
        
        Args:
            bucket_name: Source bucket name
            object_name: Object name in MinIO
            file_path: Local path to save the file
            
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self.client.fget_object(bucket_name, object_name, file_path)
            return True
        except S3Error as e:
            print(f"Error downloading {object_name} from {bucket_name}: {e}")
            return False 
