# DatorHub - Multimodal Data Management and Sharing Platform

DatorHub is an advanced web-based data sharing platform designed for managing, analyzing and publishing multimodal datasets. Originally developed as orx-surgdatahub, DatorHub has evolved to support a broader scope, extending beyond surgical data to accommodate general datasets and AI/ML workflows.

Key Components
1. ORX-Experiments
- Manages and structures multimodal data collected from OR-X data hubs during surgical experiments.
- Efficiently handles heterogeneous data formats from diverse sources, including images, videos, sensor data, and metadata.
- Ensures data consistency and traceability across experiments.

2. ORX-Datasets
- Aggregates individual surgical experiments into well-curated datasets.
- Securely hosts datasets in the public cloud for open research access.
- Provides structured metadata and version control to maintain data integrity.


## Core Features
 - Multimodal Data Management: Integrates data from surgical experiments and AI workflows, including videos, sensor logs, and clinical notes.
 - Dataset Curation: Converts raw experimental data into structured, sharable datasets.
 - Cloud Hosting: Utilizes the public cloud for secure and scalable data storage.
 - AI/ML Workflow Support: Facilitates data-driven research by integrating with AI tools at the ETH AI Center.
 - Web-Based Interface: User-friendly interface for managing, uploading, and accessing datasets.


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

