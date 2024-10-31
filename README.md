# CoreDataHub
Core data stack to store objects and query the data warehouse with MinIO and DuckDB.


## Installation
Using Docker to Set Up DuckDB and MinIO Services

### 1. Launch Docker Compose Services
To start both DuckDB and MinIO, run:

```bash
sudo docker-compose up -d --build
```

### 2. Verify MinIO Service
After starting the services, confirm that MinIO is running:

+ List running containers: `docker ps`
+ Check MinIO logs to verify proper startup: `docker-compose logs minio`

### 3. Access MinIO Console
+ Open a web browser and go to http://localhost:9001 to access the MinIO console.
+ Optionally, verify MinIO setup using the mc CLI:
```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc admin info local
```

### 4. Access DuckDB Service
+ Connect to the DuckDB service using a SQL client or the DuckDB CLI:
```bash
sudo docker exec -it duckdb duckdb
```

## Testing MinIO and DuckDB Functionality

### 1. Loading Data into MinIO

+ Step 1: Download and Prepare Dataset
    1. Download the **Hotel Booking Demand** dataset and save it as `hotel_bookings.csv` in a `data` directory.
        + Dataset Link: [Hotel Booking Demand](https://www.kaggle.com/datasets/jessemostipak/hotel-booking-demand?ref=blog.min.io)
    (Optional) Review dataset metadata in Croissant format:
    2. Metadata Link: Croissant Metadata 

+ Step 2: Configure MinIO
    1. Create a bucket named `bookings` in MinIO.
    2. Install the MinIO Python client: `pip install minio`
    3. Create a script to upload data to MinIO. Save the following as `upload_to_minio.py` in a `src` directory:
        ```python
        from minio import Minio
        from minio.error import S3Error

        # MinIO client configuration
        minio_client = Minio(
            "localhost:9000",  # MinIO address
            access_key="minioadmin",  # Access key from docker-compose
            secret_key="minioadmin",  # Secret key from docker-compose
            secure=False
        )

        # Define file and bucket details
        file_path = "../data/hotel_bookings.csv"
        bucket_name = "bookings"
        object_name = "hotel_bookings.csv"

        try:
            if not minio_client.bucket_exists(bucket_name):
                print(f"Bucket '{bucket_name}' does not exist. Please create it first.")
            else:
                minio_client.fput_object(bucket_name, object_name, file_path)
                print(f"File '{file_path}' uploaded to bucket '{bucket_name}' as '{object_name}'.")
        except S3Error as e:
            print(f"Error occurred: {e}")
        ```
    4. Start Docker services, if not already running:
        `sudo docker-compose up -d --build`
    5. Run the upload script:
        `python upload_to_minio.py`

### 2. Querying Data in MinIO Using DuckDB
DuckDB can connect to MinIO to query data using the httpfs extension, which enables access to object storage over HTTP/S.

+ Step 1: Install DuckDB and Required Packages
    `pip install duckdb numpy pandas`

+ Step 2: Configure DuckDB for MinIO Access:
    1. Create a script to configure DuckDB and query MinIO. Save the following as `minio_duckdb_query.py` in a `src` directory:
        ```python
        import duckdb
        # Load DuckDB's httpfs extension for HTTP/S access
        duckdb.sql("INSTALL httpfs")
        duckdb.sql("LOAD httpfs")

        # Configure DuckDB for MinIO access
        duckdb.sql("SET s3_region='us-east-1'")
        duckdb.sql("SET s3_access_key_id='minioadmin'")
        duckdb.sql("SET s3_secret_access_key='minioadmin'")
        duckdb.sql("SET s3_endpoint='minio:9000'")  # Use Docker service name
        duckdb.sql("SET s3_url_style='path'")
        duckdb.sql("SET s3_use_ssl=false")

        # Query the MinIO bucket data
        query = """
            SELECT * FROM read_csv_auto('s3://bookings/hotel_bookings.csv')
            LIMIT 10;
        """
        results = duckdb.query(query).to_df()
        print(results)
        ```
    
    2. Ensure Docker services are running, then run the script within the DuckDB container:
    `python minio_duckdb_query.py`


Notes:
+ For local setup, use localhost:9000 as the MinIO endpoint.
+ For inter-container communication in Docker Compose, use minio:9000 (the service name).