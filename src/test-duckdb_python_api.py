import duckdb
import pandas as pd
import os
import glob


#####################################
## Uncomment the following lines to debug the DuckDB server
###################################
## Checking that duckdb is running
pandas_df = pd.DataFrame({"a": [42]})
duckdb.sql("SELECT * FROM pandas_df")
print(duckdb.sql("SELECT * FROM pandas_df").fetchall())

# ###################################
# ## Checking that the data descriptor JSON files can be read using the
# if os.path.exists("/coralord/src/data/descriptorExample1.json"):
#     duckdb.read_json("/coralord/src/data/descriptorExample1.json")
#     ## Directly read a JSON file from within SQL:
#     print(duckdb.sql("SELECT * FROM '/coralord/src/data/descriptorExample1.json'").fetchall())
#     ## Call read_json from within SQL:
#     print(duckdb.sql("SELECT * FROM read_json_auto('/coralord/src/data/descriptorExample1.json')").fetchall())
# else:
#     print("File not found")
# ####################################


# #####################################
# ## Composing the data descriptor catalog
# data_files = glob.glob('/coralord/src/data/**/*', recursive=True)

# ## Add the data files to the catalog
# for file in data_files:
#     if file.endswith(".json"):
#         print(file)
#         duckdb.read_json(file)
#         print(duckdb.sql(f"SELECT * FROM '{file}'").fetchall())



