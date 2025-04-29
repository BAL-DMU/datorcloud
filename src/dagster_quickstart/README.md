# Dagster Component-Oriented Workflow

This directory contains a component-oriented workflow setup using Dagster, an open-source data orchestration tool. The structure follows best practices for organizing data pipelines into reusable components.

## Directory Structure

```
src/dagster_quickstart/
├── components/               # Reusable asset components
│   ├── data_processing.py    # Data processing assets
│   └── ...
├── jobs/                     # Job definitions
│   ├── data_processing_job.py
│   └── ...
├── data/                     # Data storage directory
├── definitions.py            # Main Dagster definitions file
├── workspace.yaml            # Dagster workspace configuration
└── README.md                 # This file
```

## Available Components

### Data Processing

The `components/data_processing.py` module provides the following assets:

- `raw_data`: Loads data from a CSV file (creates sample data if none exists)
- `processed_data`: Processes the raw data by adding age_group categorization
- `data_summary`: Generates summary statistics from the processed data

## Available Jobs

### Data Processing Jobs

The `jobs/data_processing_job.py` module defines the following jobs:

- `process_data_job`: Processes all data assets in sequence (raw_data → processed_data → data_summary)
- `generate_summary_job`: Only generates the summary from existing processed data

## Configuration

Components use Dagster's Config classes for configuration. For example, the `DataProcessingConfig` class allows you to configure:

- Input and output file paths
- Age bins and labels for categorization

## Running Workflows

### From Dagster UI

1. Access the Dagster UI at http://localhost:3030
2. Navigate to the Jobs tab
3. Select a job and click "Launch Run"

### From datorcloud-cli

Run the provided example script in the datorcloud-cli container:

```bash
docker exec -it datorcloud-cli bash /app/examples/run_dagster_component_workflow.sh
```

This interactive script will:
1. Check if Dagster is running
2. List available jobs
3. Let you select which job to run
4. Execute the job and monitor its progress

### Programmatically

You can also trigger jobs programmatically using the Python client:

```python
from examples.run_dagster_component_workflow import DagsterClient

client = DagsterClient("http://dagster:3030")
job_name = "process_data_job"
run_id = client.launch_job(job_name)
print(f"Job launched with run ID: {run_id}")
```

## Complete Command Sequence

Here's a complete sequence of commands to check the Dagster quickstart functionality:

1. Check if Docker containers are running:
```bash
docker ps
```

2. If Dagster is not running, start the containers:
```bash
docker-compose up -d
```

3. Check if the Dagster UI is accessible by opening:
http://localhost:3030

4. To run the example workflow using the provided script:
```bash
docker exec -it datorcloud-cli bash /app/examples/run_dagster_component_workflow.sh
```

5. To check the Dagster logs:
```bash
docker logs dagster
```

6. To connect to the Dagster container for debugging:
```bash
docker exec -it dagster bash
```

7. To check the available jobs in the Dagster UI:
- Open http://localhost:3030
- Navigate to the Jobs tab
- You should see:
  - `process_data_job`: Processes all data assets in sequence
  - `generate_summary_job`: Generates summary from existing processed data

8. To run a specific job from the command line:
```bash
docker exec -it datorcloud-cli python /app/examples/run_dagster_component_workflow.py
```

9. To check the data processing results:
```bash
docker exec -it dagster ls /app/data
```

10. If you need to rebuild the Dagster image:
```bash
bash build/dagster/build_and_save.sh
docker load -i docker/dagster_image.tar
docker-compose down
docker-compose up -d
```

Troubleshooting commands:
- Check container status: `docker ps | grep dagster`
- View detailed logs: `docker logs dagster`
- Check for Python import errors: `docker logs dagster | grep -i error`
- Verify network connectivity: `docker exec -it dagster ping dagster`

Remember:
- The Dagster UI should be accessible at http://localhost:3030
- All data processing jobs can be monitored through the UI
- The example script provides an interactive way to run jobs
- If you encounter any issues, check the container logs for detailed error messages

## Adding New Components

1. Create a new file in the `components/` directory
2. Define assets using the `@asset` decorator
3. Use dependencies with `deps=[other_asset]` to create pipeline connections
4. Import your assets in `definitions.py` and add them to the Definitions object

## Adding New Jobs

1. Create a new file in the `jobs/` directory
2. Define jobs using `define_asset_job` and select assets with `AssetSelection`
3. Import your jobs in `definitions.py` and add them to the Definitions object

## Troubleshooting

If you encounter issues with Dagster:

1. Check if the container is running: `docker ps | grep dagster`
2. Check container logs: `docker logs dagster`
3. Connect to the container: `docker exec -it dagster bash`
4. Verify the Dagster UI is accessible at http://localhost:3030
5. Check for Python import errors in the logs

### Build Errors

If you encounter build errors when building the Dagster Docker image:

- **sklearn vs scikit-learn**: The 'sklearn' package is deprecated. The Dockerfile has been updated to use 'scikit-learn' instead.
- **PYTHONPATH errors**: The Dockerfile properly initializes the PYTHONPATH environment variable.
- **Network timeouts**: If you experience network timeouts during the build process, the Dockerfile has been updated to:
  - Split installations into smaller batches
  - Add longer timeouts and retry options
  - Install larger packages like NumPy and Pandas separately

If you still encounter network issues during the build:
```bash
# Option 1: Try rebuilding with the updated Dockerfile
bash build/dagster/build_and_save.sh

# Option 2: Add a network retry tool like 'timeout' or 'retry'
timeout 600 bash build/dagster/build_and_save.sh

# Option 3: Use a different Python base image with pre-installed data science libraries
# (Modify the Dockerfile to use python:3.10-slim instead of ubuntu:22.04)
```

To rebuild after fixing these issues:
```bash
bash build/dagster/build_and_save.sh
docker load -i docker/dagster_image.tar
docker-compose down
docker-compose up -d
```

## Related Files

- **Dockerfile**: `build/dagster/Dockerfile`
- **Docker Compose**: `docker-compose.yml` (dagster service)
- **Example Scripts**: 
  - `examples/run_dagster_component_workflow.py`
  - `examples/run_dagster_component_workflow.sh` 