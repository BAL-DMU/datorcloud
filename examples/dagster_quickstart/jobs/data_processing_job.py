"""
Job definitions for data processing.
"""
from dagster import define_asset_job, AssetSelection

# Import the assets from the components
from examples.dagster_quickstart.components.data_processing import (
    raw_data,
    processed_data,
    data_summary,
)

# Define a job that processes all data assets
process_data_job = define_asset_job(
    name="process_data_job", 
    selection=AssetSelection.assets(raw_data, processed_data, data_summary)
)

# Define a job that only generates the summary
generate_summary_job = define_asset_job(
    name="generate_summary_job",
    selection=AssetSelection.assets(data_summary)
) 