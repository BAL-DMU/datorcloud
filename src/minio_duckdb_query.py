import duckdb

# Install and load httpfs extension
duckdb.sql("INSTALL httpfs")
duckdb.sql("LOAD httpfs")

# Configure DuckDB for MinIO
duckdb.sql("SET s3_region='us-east-1'")
duckdb.sql("SET s3_access_key_id='minioadmin'")
duckdb.sql("SET s3_secret_access_key='minioadmin'")
duckdb.sql("SET s3_endpoint='localhost:9000'")  # Remove "http://"
duckdb.sql("SET s3_url_style='path'")
duckdb.sql("SET s3_use_ssl=false")  # Disable SSL if using HTTP

# Query data from MinIO
query = """
    SELECT * FROM read_csv_auto('s3://bookings/hotel_bookings.csv')
    LIMIT 10;
"""

# Execute query and display results
results = duckdb.query(query).to_df()
print(results)
