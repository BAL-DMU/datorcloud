
import duckdb
import pandas as pd
import os
import glob
import json

# ########################################
# ## Uncomment the following lines to debug the DuckDB server
# ########################################
# ## Checking that duckdb is running
# pandas_df = pd.DataFrame({"a": [42]})
# duckdb.sql("SELECT * FROM pandas_df")
# print(duckdb.sql("SELECT * FROM pandas_df").fetchall())

# ########################################
# ## Checking that the data descriptor JSON files can be read using the
# if os.path.exists("/coralord/src/data/descriptorExample1.json"):
#     duckdb.read_json("/coralord/src/data/descriptorExample1.json")
#     ## Directly read a JSON file from within SQL:
#     print(duckdb.sql("SELECT * FROM '/coralord/src/data/descriptorExample1.json'").fetchall())
#     ## Call read_json from within SQL:
#     print(duckdb.sql("SELECT * FROM read_json_auto('/coralord/src/data/descriptorExample1.json')").fetchall())
# else:
#     print("File not found")
# ########################################


########################################
########################################
## Composing the data descriptor catalog

# Create or connect to the database
db = duckdb.connect('dataDescriptorCatalog.db')

# Create a table to store the descriptor metadata, storing the list as TEXT
db.execute('''
    CREATE TABLE IF NOT EXISTS DescriptorMetadata (
        name TEXT,
        url TEXT,
        files TEXT,  -- Store the list of files as a string
        pipeline TEXT,
        docker TEXT
    );
''')

# Function to insert JSON descriptor metadata into the database
def insert_descriptor_metadata(json_file_path):
    with open(json_file_path, 'r') as file:
        data = json.load(file)
        metadata = data['descriptor']['metadata']
        
        # Convert the files list to a string (e.g., comma-separated or JSON string)
        files_str = json.dumps(metadata['files'])
        
        # Insert the metadata into the DuckDB table
        db.execute('''
            INSERT INTO DescriptorMetadata (name, url, files, pipeline, docker)
            VALUES (?, ?, ?, ?, ?)
        ''', (metadata['name'], 
              metadata['url'], 
              files_str,  # Insert the files as a string
              metadata['pipeline'], 
              metadata['docker']))

# Insert all JSON files from a specific directory
data_files = glob.glob('/coralord/src/data/**/*.json', recursive=True)

for file in data_files:
    if os.path.exists(file):
        insert_descriptor_metadata(file)

# Query the database to confirm insertion
results = db.execute('SELECT * FROM DescriptorMetadata').fetchall()
print('Printting dataDescriptorCatalog.db ->')
for row in results:
    print(row)