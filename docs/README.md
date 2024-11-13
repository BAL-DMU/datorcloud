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

- `material` 
- `readthedocs` (used)
- `mkdocs`

### 3. Example `mkdocs.yml`

```yaml
site_name: ORX-SurgDataHub Docs
site_description: Documentation for the ORX-SurgDataHub platform
site_author: Digital Medicine Unit/OR-X Translational Center for Surgery/Balgrist University Hospital

nav:
  - Overview: 01_overview/overview.md
  - Installation: 02_installation/CoreDataPlatform.md

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