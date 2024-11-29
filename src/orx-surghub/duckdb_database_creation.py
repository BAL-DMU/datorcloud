import duckdb

def create_database():
    """
    Creates a new database called ORXExperiments if it doesn't exist.
    Returns a connection to the database.
    """
    # Connect to or create the database
    conn = duckdb.connect('ORXExperiments.ddb')
    return conn

def create_experiment_card_table(conn):
    """
    Creates the ExperimentCard table if it doesn't exist.
    
    Parameters:
    conn: duckdb.DuckDBPyConnection - Connection to the database
    """
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ExperimentCard (
        experiment_id INTEGER PRIMARY KEY,
        name VARCHAR,
        or_tasks VARCHAR,
        modalities VARCHAR,
        formats VARCHAR,
        public BOOLEAN,
        size VARCHAR,
        devicess VARCHAR
    )
    """)

def create_file_object_metadata_table(conn):
    """
    Creates the FileObjectMetadata table if it doesn't exist.
    
    Parameters:
    conn: duckdb.DuckDBPyConnection - Connection to the database
    """
    conn.execute("""
    CREATE TABLE IF NOT EXISTS FileObjectMetadata (
        file_id INTEGER PRIMARY KEY,
        experiment_id INTEGER,
        subfolder VARCHAR,
        file_name VARCHAR,
        file_path VARCHAR,
        file_format VARCHAR,
        timestamp TIMESTAMP,
        FOREIGN KEY (experiment_id) REFERENCES ExperimentCard(experiment_id)
    )
    """)

def main():
    # Create database and get connection
    conn = create_database()
    
    try:
        # Create tables
        create_experiment_card_table(conn)
        create_file_object_metadata_table(conn)
        print("Database and tables created successfully!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        
    finally:
        # Close the connection
        conn.close()

if __name__ == "__main__":
    main()