# datorcloud - Multimodal Data Management and Sharing Platform

**DatorCloud** is a lightweight, self-hosted cloud platform developed at Balgrist University Hospital and the OR-X Translational Center for Surgery. It simplifies the management, querying, and sharing of multimodal research data—including images, videos, sensor data, and clinical records—using **DuckDB** for fast, SQL-like analytics and **MinIO** for S3-compatible object storage.

Designed for research teams and institutions, DatorCloud offers a modular and scalable solution for organizing and exploring complex datasets without requiring heavy infrastructure.

### Key Features
- **Multimodal Data Management**: Organize and access diverse datasets in a structured, web-based environment.
- **Unified Dataset Catalog**: Browse and manage datasets by project, researcher, or experimental context.
- **Custom Dataset Composition**: Create tailored datasets using SQL-like queries over object storage.
- **Efficient, Traceable Access**: Query large datasets directly with DuckDB and MinIO CLIs, reducing duplication and enabling reproducible analysis.

Key Components
1. Experiments
- Manages and structures multimodal data collected from OR-X data hubs during surgical experiments.
- Efficiently handles heterogeneous data formats from diverse sources, including images, videos, sensor data, and metadata.
- Ensures data consistency and traceability across experiments.

2. Datasets
- Aggregates individual surgical experiments into well-curated datasets.
- Securely hosts datasets in the public cloud for open research access.
- Provides structured metadata and version control to maintain data integrity.



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

