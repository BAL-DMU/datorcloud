import duckdb

# Install and load the httpfs extension for HTTP/S access
duckdb.sql("INSTALL httpfs")
duckdb.sql("LOAD httpfs")

# Configure DuckDB to access MinIO
duckdb.sql("SET s3_region='us-east-1'")
duckdb.sql("SET s3_access_key_id='minioadmin'")
duckdb.sql("SET s3_secret_access_key='minioadmin'")
duckdb.sql("SET s3_endpoint='localhost:9000'")  # Update if MinIO is not on localhost
duckdb.sql("SET s3_url_style='path'")
duckdb.sql("SET s3_use_ssl=false")  # Set to true if using HTTPS

# Specify the path to the CSV file in MinIO
file_path = "s3://orx-metadata/metadata_orx-datahub.csv"

# Query CSV data from MinIO
try:
    # Adjust the query to read data from the CSV file
    query = f"""
        SELECT * FROM read_csv_auto('{file_path}')
        LIMIT 10;
    """
    
    # Run the query and fetch results
    results = duckdb.query(query).to_df()
    print(results)
except duckdb.IOException as e:
    print(f"An error occurred while querying data: {e}")
