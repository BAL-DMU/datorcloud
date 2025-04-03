# Surgical Data Cloud Platform - SDCHub

A Surgical Data Cloud Platform for Managing and Populate Multimodal Datasets

## Deployment

### Launch Docker Compose Services

To start both DuckDB and MinIO services, run:

```bash
sudo docker-compose up -d --build
```

Notes:
    + For local setup, use localhost:9000 as the MinIO endpoint.
    + For inter-container communication in Docker Compose, use minio:9000 (the service name).

### Conda Enviroment

Create a new conda environment with the following command:
`conda create -n orx-surghub python=3.10.14`

Actiavte the environment with the following command:
`conda activate orx-surghub`

Install the required packages with the following command:
`pip install -r requirements.txt`

