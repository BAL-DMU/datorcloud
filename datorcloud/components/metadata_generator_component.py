import os
import csv
import re
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd


class MetadataGeneratorComponent:
    """Component for generating and managing metadata from datasets and experiments."""
    
    def __init__(self):
        """Initialize the metadata generator component."""
        # Pattern to extract frame number from filenames (e.g. camera01_colorimage-000031.jpg -> 31)
        self.frame_pattern = re.compile(r'-(\d+)\.')
    
    def extract_frame_number(self, filename: str) -> Optional[int]:
        """
        Extract the frame number from a filename.
        
        Args:
            filename: The filename to process
            
        Returns:
            The extracted frame number or None if not found
        """
        match = self.frame_pattern.search(filename)
        if match:
            return int(match.group(1))
        return None
    
    def extract_camera_info(self, path_parts: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract camera ID and image type from path components.
        
        Args:
            path_parts: List of path components
            
        Returns:
            Tuple of (camera_id, image_type) or (None, None) if not found
        """
        camera_id = None
        image_type = None
        
        for part in path_parts:
            if part.startswith('camera'):
                camera_id = part
            elif part in ['colorimage', 'depthimage']:
                image_type = part
        
        return camera_id, image_type
    
    def collect_dataset_metadata(
        self, 
        dataset_name: str, 
        base_dir: str
    ) -> List[Dict[str, Any]]:
        """
        Collect metadata for a dataset.
        
        Args:
            dataset_name: Name of the dataset
            base_dir: Base directory containing the dataset
            
        Returns:
            List of metadata records as dictionaries
        """
        metadata_records = []
        
        if not os.path.exists(base_dir):
            print(f"Dataset directory '{base_dir}' does not exist.")
            return metadata_records
            
        for experiment in os.listdir(base_dir):
            experiment_path = os.path.join(base_dir, experiment)
            
            # Only process directories
            if os.path.isdir(experiment_path):
                for root, _, files in os.walk(experiment_path):
                    # Generate relative subfolder path from the experiment folder
                    subfolder = os.path.relpath(root, experiment_path)
                    
                    # Extract path parts for parsing camera and image type
                    path_parts = subfolder.split(os.sep)
                    camera_id, image_type = self.extract_camera_info(path_parts)
                    
                    for file_name in files:
                        file_path = os.path.join(subfolder, file_name)  # Relative path from experiment root
                        file_format = os.path.splitext(file_name)[1].lstrip('.').lower()
                        frame_number = self.extract_frame_number(file_name)
                        
                        # Collect metadata for each file
                        metadata_records.append({
                            "dataset": dataset_name,
                            "experiment": experiment,
                            "subfolder": subfolder,
                            "file_name": file_name,
                            "file_path": file_path,
                            "file_format": file_format,
                            "camera_id": camera_id,
                            "image_type": image_type,
                            "frame_number": frame_number
                        })
        
        return metadata_records
    
    def generate_metadata(
        self, 
        dataset_dirs: Dict[str, str],
        output_file: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Generate metadata for multiple datasets.
        
        Args:
            dataset_dirs: Dictionary mapping dataset names to directory paths
            output_file: Optional path to save metadata CSV
            
        Returns:
            DataFrame containing the collected metadata
        """
        all_metadata = []
        
        # Collect metadata from all datasets
        for dataset_name, base_dir in dataset_dirs.items():
            dataset_metadata = self.collect_dataset_metadata(dataset_name, base_dir)
            all_metadata.extend(dataset_metadata)
        
        # Convert to DataFrame
        metadata_df = pd.DataFrame(all_metadata)
        
        # Optionally save to file
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            metadata_df.to_csv(output_file, index=False)
            print(f"Metadata file '{output_file}' generated successfully.")
        
        return metadata_df 
