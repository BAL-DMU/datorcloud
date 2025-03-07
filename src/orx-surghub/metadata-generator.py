import os
import csv
import re

# Define the base directories for the datasets
base_dirs = {
    "4dor-dataset": "./data/4dor-dataset",
    "orx-dataset": "./data/orx-dataset"
}

# Output metadata file
output_file = "data/metadata_orx-datahub.csv"

# List to hold all metadata records
metadata = []

# Regular expression to extract frame number from filenames
# Example: camera01_colorimage-000031.jpg -> 31
frame_pattern = re.compile(r'-(\d+)\.')

def extract_frame_number(filename):
    """
    Extract the frame number from the filename.
    
    Parameters:
    - filename: The filename to extract the frame number from.
    
    Returns:
    - The frame number as an integer, or None if not found.
    """
    match = frame_pattern.search(filename)
    if match:
        return int(match.group(1))
    return None

def extract_camera_info(path_parts):
    """
    Extract camera information from the path parts.
    
    Parameters:
    - path_parts: List of path components.
    
    Returns:
    - A tuple containing (camera_id, image_type) or (None, None) if not found.
    """
    camera_id = None
    image_type = None
    
    for part in path_parts:
        if part.startswith('camera'):
            camera_id = part
        elif part in ['colorimage', 'depthimage']:
            image_type = part
    
    return camera_id, image_type

def collect_metadata(dataset_name, base_dir):
    """
    Collect metadata for each experiment in a dataset.

    Parameters:
    - dataset_name: The name of the dataset (e.g., '4dor-dataset').
    - base_dir: The base directory of the dataset.
    """
    for experiment in os.listdir(base_dir):
        experiment_path = os.path.join(base_dir, experiment)
        
        # Only process directories
        if os.path.isdir(experiment_path):
            for root, dirs, files in os.walk(experiment_path):
                # Generate relative subfolder path from the experiment folder
                subfolder = os.path.relpath(root, experiment_path)
                
                # Extract path parts for parsing camera and image type
                path_parts = subfolder.split(os.sep)
                camera_id, image_type = extract_camera_info(path_parts)
                
                for file_name in files:
                    file_path = os.path.join(subfolder, file_name)  # Relative path from experiment root
                    file_format = os.path.splitext(file_name)[1].lstrip('.').lower()  # Extract file extension
                    frame_number = extract_frame_number(file_name)
                    
                    # Collect metadata for each file
                    metadata.append({
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

# Collect metadata from all datasets
for dataset_name, base_dir in base_dirs.items():
    if os.path.exists(base_dir):
        collect_metadata(dataset_name, base_dir)
    else:
        print(f"Dataset directory '{base_dir}' does not exist.")

# Write metadata to a CSV file
with open(output_file, mode="w", newline="") as csvfile:
    fieldnames = [
        "dataset", "experiment", "subfolder", "file_name", "file_path", 
        "file_format", "camera_id", "image_type", "frame_number"
    ]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(metadata)

print(f"Metadata file '{output_file}' generated successfully.")