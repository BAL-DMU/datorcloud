import os
import shutil

def restructure_folder(old_root: str, new_root: str):
    # Ensure new root exists
    os.makedirs(new_root, exist_ok=True)
    
    # Iterate over data types (colorimage, depthimage)
    for data_type in os.listdir(old_root):
        data_type_path = os.path.join(old_root, data_type)
        
        if os.path.isdir(data_type_path):
            # Iterate over device folders (camera01, camera02, etc.)
            for camera in os.listdir(data_type_path):
                camera_path = os.path.join(data_type_path, camera)
                
                if os.path.isdir(camera_path):
                    # Define new camera directory
                    new_camera_path = os.path.join(new_root, camera, data_type)
                    os.makedirs(new_camera_path, exist_ok=True)
                    
                    # Move files to the new structure
                    for file in os.listdir(camera_path):
                        old_file_path = os.path.join(camera_path, file)
                        new_file_path = os.path.join(new_camera_path, file)
                        shutil.move(old_file_path, new_file_path)
                    
    print("Restructuring completed successfully!")

# Define paths
old_structure_path = "data/orx-dataset/experiment-1"
new_structure_path = "data/orx-experiments/experiment-1"

# Run restructuring function
restructure_folder(old_structure_path, new_structure_path)
