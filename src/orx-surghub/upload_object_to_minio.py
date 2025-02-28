from minio import Minio
from minio.error import S3Error
import os

# MinIO client configuration
minio_client = Minio(
    # "localhost:9000",             # Update with your MinIO address if different
    "minio:9000",                   # Update with your MinIO address if different
    access_key="minioadmin",        # Access key (set in docker-compose)
    secret_key="minioadmin",        # Secret key (set in docker-compose)
    secure=False                    # Use True if using HTTPS
)

# Define the MinIO bucket name
# bucket_name = "orx-datalake"
bucket_name = "orx-experiments"

# Create bucket if it does not exist
try:
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)
        print(f"Bucket '{bucket_name}' created.")
    else:
        print(f"Bucket '{bucket_name}' already exists.")
except S3Error as err:
    print(f"Error creating bucket: {err}")

# Recursive function to upload files while preserving the folder structure
def upload_directory_to_minio(local_directory, minio_bucket, prefix=""):
    """
    Recursively upload files from a local directory to a MinIO bucket,
    preserving the folder structure using prefixes.
    
    Parameters:
    - local_directory (str): Path to the local directory to upload.
    - minio_bucket (str): Name of the MinIO bucket.
    - prefix (str): Prefix for MinIO object names to preserve directory structure.
    """
    for root, dirs, files in os.walk(local_directory):
        for file in files:
            # Construct the full local path to the file
            local_path = os.path.join(root, file)
            
            # Construct the MinIO object name by combining prefix with relative path
            relative_path = os.path.relpath(local_path, local_directory)
            minio_object_name = os.path.join(prefix, relative_path).replace("\\", "/")  # Normalize path for MinIO

            # Upload the file to MinIO with the constructed object name
            try:
                minio_client.fput_object(
                    minio_bucket, minio_object_name, local_path
                )
                print(f"Uploaded '{local_path}' as '{minio_object_name}' to '{minio_bucket}'")
            except S3Error as e:
                print(f"Error uploading '{local_path}': {e}")

# Define dataset root directories and prefixes for each
dataset_paths = {
    "4dor-dataset": "./data/4dor-dataset",
    "orx-experiments": "./data/orx-experiments"
}

# Upload each dataset to MinIO with its respective folder structure as a prefix
for dataset_name, dataset_path in dataset_paths.items():
    # Ensure the dataset path exists locally
    if os.path.exists(dataset_path):
        upload_directory_to_minio(dataset_path, bucket_name, prefix=dataset_name)
    else:
        print(f"Dataset path '{dataset_path}' does not exist.")
