import os
import csv

# Define the base directories for the datasets
base_dirs = {
    "4dor-dataset": "./data/4dor-dataset",
    "orx-dataset": "./data/orx-dataset"
}

# Output metadata file
output_file = "data/metadata_orx-datahub.csv"

# List to hold all metadata records
metadata = []

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
                
                for file_name in files:
                    file_path = os.path.join(subfolder, file_name)  # Relative path from experiment root
                    file_format = os.path.splitext(file_name)[1].lstrip('.').lower()  # Extract file extension
                    
                    # Collect metadata for each file
                    metadata.append({
                        "dataset": dataset_name,
                        "experiment": experiment,
                        "subfolder": subfolder,
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_format": file_format
                    })

# Collect metadata from all datasets
for dataset_name, base_dir in base_dirs.items():
    if os.path.exists(base_dir):
        collect_metadata(dataset_name, base_dir)
    else:
        print(f"Dataset directory '{base_dir}' does not exist.")

# Write metadata to a CSV file
with open(output_file, mode="w", newline="") as csvfile:
    fieldnames = ["dataset", "experiment", "subfolder", "file_name", "file_path", "file_format"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(metadata)

print(f"Metadata file '{output_file}' generated successfully.")
