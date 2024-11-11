# MkDocs Quick Setup Guide

## Requirements

- Python 3.7+
- pip (Python package manager)
- Git

## Installation

`python -m pip install mkdocs mkdocs-material plantuml-markdown pymdown-extensions`

## Configuration

### 1. Create New Project

`mkdocs new my-project
cd my-project`

### 2. Choose Theme

Available themes:

- `material` (recommended)
- `readthedocs`
- `mkdocs`

### 3. Example `mkdocs.yml`

```yaml
site_name: ORX-SurgHub Docs
site_description: Documentation for the ORX-SurgHub platform
site_author: Digital Medicine Unit/OR-X Translational Center for Surgery/Balgrist University Hospital

nav:
  - Overview: 01_overview/orx-surghub_architecture_and_development_plan.md
  - Specifications: 02_specifications/spec_01.md
  - Methods:
    - Technical Design: 03_methods/method1_4_spec1.md
  - Implementations:
    - Prerequisites: 04_implementations/spec1-01_prerequisites.md
    - Data Ingestion: 04_implementations/spec1-02_airflow_dag_4_data_ingestion.md
    - Directory Structure: 04_implementations/spec1-03_establish_directory_structure_in_minio.md
    - Database Schema: 04_implementations/spec1-04_define_the_database_schema_in_postgresql.md

theme:
  name: readthedocs
  navigation_depth: 1
  collapse_navigation: false
  titles_only: false

markdown_extensions:
  - plantuml_markdown:
      server: http://www.plantuml.com/plantuml
  - toc:
      permalink: true
  - admonition
  - pymdownx.details
  - pymdownx.superfences

plugins:
  - search

extra:
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/BAL-DMU/orx-surghub

copyright: '&copy; 2024 Balgrist University Hospital'

```

## Deployment

### Local Development

`mkdocs serve  *# Run at http://localhost:8000*`

### GitHub Pages

1. Push to GitHub:

```bash
git init
git add .
git commit -m "Initial docs"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

1. Deploy:

`mkdocs gh-deploy  *# Deploys to gh-pages branch*`

Access at: `https://<username>.github.io/<repository>`