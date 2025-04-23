import duckdb
import pandas as pd
from typing import Optional, Dict, List, Any, Union


class QueryComponent:
    """Component for querying metadata using DuckDB."""
    
    def __init__(
        self,
        s3_region: str = "us-east-1",
        s3_endpoint: str = "minio:9090",
        s3_access_key: str = "minioadmin",
        s3_secret_key: str = "minioadmin",
        s3_use_ssl: bool = False
    ):
        """
        Initialize the DuckDB query component with MinIO S3 configuration.
        
        Args:
            s3_region: The S3 region
            s3_endpoint: MinIO server endpoint
            s3_access_key: MinIO access key
            s3_secret_key: MinIO secret key
            s3_use_ssl: Whether to use SSL for S3 connections
        """
        self.conn = duckdb.connect(":memory:")
        self._configure_httpfs()
        self._configure_s3(
            s3_region, 
            s3_endpoint, 
            s3_access_key, 
            s3_secret_key, 
            s3_use_ssl
        )
    
    def _configure_httpfs(self) -> None:
        """Load the httpfs extension for HTTP/S access."""
        try:
            # Try to load the extension from standard location first
            self.conn.execute("LOAD httpfs")
            print("HTTPFS loaded successfully")
        except Exception as e:
            # Fall back to loading from specific path
            try:
                self.conn.execute(
                    "LOAD '/root/.duckdb/extensions/v1.2.0/linux_amd64_gcc4/httpfs.duckdb_extension'"
                )
                print("HTTPFS loaded successfully from specific path")
            except Exception as e2:
                print(f"Error loading HTTPFS extension: {e2}")
                raise RuntimeError("Failed to load httpfs extension") from e2
    
    def _configure_s3(
        self,
        s3_region: str,
        s3_endpoint: str,
        s3_access_key: str,
        s3_secret_key: str,
        s3_use_ssl: bool
    ) -> None:
        """
        Configure DuckDB S3 settings.
        
        Args:
            s3_region: The S3 region
            s3_endpoint: MinIO server endpoint
            s3_access_key: MinIO access key
            s3_secret_key: MinIO secret key
            s3_use_ssl: Whether to use SSL for S3 connections
        """
        self.conn.execute(f"SET s3_region='{s3_region}'")
        self.conn.execute(f"SET s3_access_key_id='{s3_access_key}'")
        self.conn.execute(f"SET s3_secret_access_key='{s3_secret_key}'")
        self.conn.execute(f"SET s3_endpoint='{s3_endpoint}'")
        self.conn.execute("SET s3_url_style='path'")
        self.conn.execute(f"SET s3_use_ssl={str(s3_use_ssl).lower()}")
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """
        Execute a DuckDB query and return results as a DataFrame.
        
        Args:
            query: SQL query to execute
            
        Returns:
            DataFrame with query results
        """
        try:
            result = self.conn.execute(query).fetchdf()
            return result
        except Exception as e:
            print(f"Error executing query: {e}")
            raise
    
    def query_metadata(
        self,
        metadata_file: str,
        filters: Dict[str, Any] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Query the metadata CSV file with optional filters.
        
        Args:
            metadata_file: S3 path to metadata CSV file
            filters: Dictionary of column:value filters to apply
            limit: Optional limit on number of results
            
        Returns:
            DataFrame with filtered metadata
        """
        # Build the query
        query = f"SELECT * FROM read_csv_auto('{metadata_file}')"
        
        # Add filters if provided
        if filters:
            where_clauses = []
            for column, value in filters.items():
                if isinstance(value, str):
                    where_clauses.append(f"{column} = '{value}'")
                elif isinstance(value, list):
                    values_str = ", ".join([f"'{v}'" for v in value if isinstance(v, str)])
                    if values_str:
                        where_clauses.append(f"{column} IN ({values_str})")
                else:
                    where_clauses.append(f"{column} = {value}")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
        
        # Add limit if provided
        if limit:
            query += f" LIMIT {limit}"
        
        return self.execute_query(query)
    
    def get_object_paths(
        self,
        metadata_file: str,
        dataset: str,
        data_bucket: str = "orx-datalake",
        **filters
    ) -> List[Dict[str, str]]:
        """
        Get S3 object paths for files matching the given criteria.
        
        Args:
            metadata_file: S3 path to metadata CSV file
            dataset: Dataset name
            data_bucket: Name of the data bucket
            **filters: Additional filter criteria (e.g., camera_id, image_type)
            
        Returns:
            List of dictionaries with object information
        """
        # Build filter dictionary
        filter_dict = {"dataset": dataset}
        filter_dict.update(filters)
        
        # Build where clause
        where_clauses = []
        for column, value in filter_dict.items():
            if isinstance(value, str):
                where_clauses.append(f"{column} = '{value}'")
            elif isinstance(value, list):
                values_str = ", ".join([f"'{v}'" for v in value])
                where_clauses.append(f"{column} IN ({values_str})")
        
        where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Query to get file paths
        query = f"""
            SELECT 
                experiment,
                's3://{data_bucket}/' || file_path AS full_path,
                file_path AS object_name,
                subfolder,
                file_name
            FROM read_csv_auto('{metadata_file}')
            {where_clause}
        """
        
        results = self.execute_query(query).to_dict('records')
        return results 
