import os
from typing import Dict, List, Optional, Any

from .minio_component import MinioObjectComponent
from .query_component import QueryComponent


class ObjectRetrievalComponent:
    """Component for retrieving data objects based on metadata queries."""
    
    def __init__(
        self,
        minio_component: MinioObjectComponent,
        query_component: QueryComponent,
        local_base_dir: str = "./retrieved_data"
    ):
        """
        Initialize the object retrieval component.
        
        Args:
            minio_component: MinIO component for downloading files
            query_component: Query component for metadata queries
            local_base_dir: Base directory for downloaded files
        """
        self.minio_component = minio_component
        self.query_component = query_component
        self.local_base_dir = local_base_dir
    
    def retrieve_objects(
        self,
        metadata_file: str,
        dataset: str,
        data_bucket: str = "orx-datalake",
        local_dir: Optional[str] = None,
        max_files: Optional[int] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Retrieve objects from MinIO based on metadata query.
        
        Args:
            metadata_file: S3 path to metadata CSV
            dataset: Dataset name
            data_bucket: Bucket containing the data
            local_dir: Optional local directory override
            max_files: Maximum number of files to retrieve
            **filters: Additional filters to apply
            
        Returns:
            List of dictionaries with information about retrieved files
        """
        # Get object paths from metadata
        object_infos = self.query_component.get_object_paths(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=data_bucket,
            **filters
        )
        
        # Limit the number of files if specified
        if max_files is not None:
            object_infos = object_infos[:max_files]
        
        # Set up the base directory
        base_dir = local_dir if local_dir else self.local_base_dir
        
        # Download each file
        downloaded_files = []
        for obj_info in object_infos:
            experiment = obj_info["experiment"]
            subfolder = obj_info["subfolder"]
            file_name = obj_info["file_name"]
            object_name = f"{dataset}/{experiment}/{subfolder}/{file_name}"
            
            # Create the local directory structure
            local_path = os.path.join(base_dir, dataset, experiment, subfolder, file_name)
            local_dir = os.path.dirname(local_path)
            os.makedirs(local_dir, exist_ok=True)
            
            # Download the file
            success = self.minio_component.download_file(
                bucket_name=data_bucket,
                object_name=object_name,
                file_path=local_path
            )
            
            downloaded_files.append({
                "object_name": object_name,
                "local_path": local_path,
                "success": success,
                "experiment": experiment,
                "dataset": dataset,
                "subfolder": subfolder,
                "file_name": file_name
            })
        
        return downloaded_files
    
    def retrieve_experiment_data(
        self,
        metadata_file: str,
        dataset: str,
        experiment: str,
        data_bucket: str = "orx-datalake",
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all data for a specific experiment.
        
        Args:
            metadata_file: S3 path to metadata CSV
            dataset: Dataset name
            experiment: Experiment name
            data_bucket: Bucket containing the data
            **filters: Additional filters to apply
            
        Returns:
            List of dictionaries with information about retrieved files
        """
        # Add experiment to filters
        filters["experiment"] = experiment
        
        return self.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=data_bucket,
            **filters
        )
    
    def retrieve_camera_data(
        self,
        metadata_file: str,
        dataset: str,
        camera_id: str,
        data_bucket: str = "orx-datalake",
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Retrieve data for a specific camera.
        
        Args:
            metadata_file: S3 path to metadata CSV
            dataset: Dataset name
            camera_id: Camera ID
            data_bucket: Bucket containing the data
            **filters: Additional filters to apply
            
        Returns:
            List of dictionaries with information about retrieved files
        """
        # Add camera_id to filters
        filters["camera_id"] = camera_id
        
        return self.retrieve_objects(
            metadata_file=metadata_file,
            dataset=dataset,
            data_bucket=data_bucket,
            **filters
        ) 
