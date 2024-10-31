
from minio import Minio
from minio.error import S3Error

# Configure MinIO client
minio_client = Minio(
    "localhost:9000",                # MinIO address
    access_key="minioadmin",         # Access key (set in docker-compose)
    secret_key="minioadmin",         # Secret key (set in docker-compose)
    secure=False                     # Set to True if using HTTPS
)

# Define file path and bucket
file_path = "../data/hotel_bookings.csv"  # Path to your CSV file
bucket_name = "bookings"               # Name of the existing bucket
object_name = "hotel_bookings.csv"      # Name under which file will be saved in MinIO

# Check if the bucket exists
try:
    if not minio_client.bucket_exists(bucket_name):
        print(f"Bucket '{bucket_name}' does not exist. Please create it first.")
    else:
        # Upload file
        minio_client.fput_object(bucket_name, object_name, file_path)
        print(f"File '{file_path}' uploaded to bucket '{bucket_name}' as '{object_name}'.")
except S3Error as e:
    print(f"Error occurred: {e}")
