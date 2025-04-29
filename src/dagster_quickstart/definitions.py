"""
Main Dagster definitions file that brings together all assets and jobs.
"""
from dagster import Definitions

# Import all assets
from src.dagster_quickstart.components.data_processing import (
    raw_data,
    processed_data,
    data_summary
)

# Import all jobs
from src.dagster_quickstart.jobs.data_processing_job import (
    process_data_job,
    generate_summary_job
)

# Define the Dagster definitions object
defs = Definitions(
    assets=[raw_data, processed_data, data_summary],
    jobs=[process_data_job, generate_summary_job]
) 