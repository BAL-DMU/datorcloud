import duckdb
import os

def create_database():
    """Creates ORXExperiments database in Docker volume"""
    db_path = '/orx-surgdatahub/data/ORXExperiments.ddb'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return duckdb.connect(db_path)

def create_experiment_card_table(conn):
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
    conn = create_database()
    try:
        create_experiment_card_table(conn)
        create_file_object_metadata_table(conn)
        print("Database and tables created successfully!")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()



# ########################################
# ## Command line to check the database
# ########################################
#
# # 1. Connect to container
# sudo docker exec -it orx-surgdatahub-duckdb-1 bash
#
# # 2. Start Python shell
# python
#
# # 3. Check database in Python shell
# import duckdb
# conn = duckdb.connect('surgdata.db')
#
# # 4. Show all tables
# conn.execute("SHOW TABLES").fetchall()
#
# # 5. View table contents (replace table_name)
# conn.execute("SELECT * FROM table_name LIMIT 5").fetchall()
#
# # 6. Exit Python shell
# exit()
#
# # 7. Exit container
# exit