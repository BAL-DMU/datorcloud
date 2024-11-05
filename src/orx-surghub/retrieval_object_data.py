import duckdb
from minio import Minio
from minio.error import S3Error
import os

# Configure MinIO client
minio_client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)

# DuckDB configuration and httpfs extension setup
duckdb.sql("INSTALL httpfs")
duckdb.sql("LOAD httpfs")
duckdb.sql("SET s3_region='us-east-1'")
duckdb.sql("SET s3_access_key_id='minioadmin'")
duckdb.sql("SET s3_secret_access_key='minioadmin'")
duckdb.sql("SET s3_endpoint='localhost:9000'")
duckdb.sql("SET s3_url_style='path'")
duckdb.sql("SET s3_use_ssl=false")

# Define paths and parameters
metadata_file = "s3://orx-metadata/metadata_orx-datahub.csv"  # Metadata file path in MinIO
local_base_dir = "./retrieved_data"  # Local base directory to save data
dataset_name = "4dor-dataset"        # Dataset to query (e.g., 4dor-dataset or orx-dataset)
camera_name = "camera01"             # Camera name to filter by

# Query metadata to get paths for images and annotations for the specified camera and dataset
try:
    query = f"""
        SELECT 
            experiment,
            's3://orx-data-lake/' || file_path AS full_path,
            subfolder
        FROM read_csv_auto('{metadata_file}')
        WHERE dataset = '{dataset_name}' 
          AND file_path LIKE '%{camera_name}_%' 
          AND (subfolder LIKE 'colorimage/%' OR subfolder LIKE 'depthimage/%')
        ORDER BY experiment, subfolder
    """
    
    # Execute the query and fetch results
    results = duckdb.query(query).to_df()
    print(f"Found {len(results)} matching files.")
    
    # Download each file and save it locally
    for index, row in results.iterrows():
        experiment = row['experiment']
        subfolder = row['subfolder']
        file_path = row['full_path']
        
        # Construct the local file path based on experiment and subfolder structure
        local_experiment_dir = os.path.join(local_base_dir, dataset_name, experiment, subfolder)
        os.makedirs(local_experiment_dir, exist_ok=True)
        
        # Extract the filename from the MinIO path
        filename = os.path.basename(file_path)
        local_file_path = os.path.join(local_experiment_dir, filename)
        
        # Construct object_name including dataset, experiment, and full subfolder path
        object_name = f"{dataset_name}/{experiment}/{subfolder}/{filename}"
        
        # Additional logging to verify paths
        print(f"Attempting to download {file_path} as {object_name} to {local_file_path}")
        
        # Download the file from MinIO to the local directory
        try:
            minio_client.fget_object(
                bucket_name="orx-datalake",
                object_name=object_name,
                file_path=local_file_path
            )
            print(f"Downloaded {file_path} to {local_file_path}")
        except S3Error as e:
            print(f"Error downloading {file_path}: {e}")

except duckdb.IOException as e:
    print(f"An error occurred while querying metadata: {e}")
