# orx-surghub
Surgical data platform to manage and release multimodal datasets for the ORD project (DuckDB)


## Installation
sudo docker-compose up -d --build

## Usage
sudo docker-compose exec duckdb /bin/bash

## Testing that the API works
python src/test-duckdb_python_api.py
