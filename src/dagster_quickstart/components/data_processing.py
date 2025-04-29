"""
Data processing components for Dagster workflows.
"""
import os
import pandas as pd
from dagster import asset, AssetIn, Config, get_dagster_logger

logger = get_dagster_logger()

class DataProcessingConfig(Config):
    """Configuration for data processing assets."""
    input_path: str = "/app/src/dagster_quickstart/data/sample_data.csv"
    output_path: str = "/app/src/dagster_quickstart/data/processed_data.csv"
    age_bins: list = [0, 30, 40, 100]
    age_labels: list = ["Young", "Middle", "Senior"]

@asset
def raw_data(config: DataProcessingConfig):
    """
    Load raw data from a CSV file.
    """
    logger.info(f"Loading data from {config.input_path}")
    
    # Create sample data if file doesn't exist
    if not os.path.exists(config.input_path):
        logger.info(f"Creating sample data at {config.input_path}")
        sample_data = pd.DataFrame({
            "id": [1, 2, 3, 4],
            "name": ["Alice", "Bob", "Charlie", "Diana"],
            "age": [28, 35, 42, 31],
            "city": ["New York", "San Francisco", "Chicago", "Los Angeles"]
        })
        
        # Make sure directory exists
        os.makedirs(os.path.dirname(config.input_path), exist_ok=True)
        sample_data.to_csv(config.input_path, index=False)
    
    # Load and return the data
    df = pd.read_csv(config.input_path)
    logger.info(f"Loaded {len(df)} rows from {config.input_path}")
    return df

@asset(deps=[raw_data])
def processed_data(raw_data: pd.DataFrame, config: DataProcessingConfig):
    """
    Process the raw data by adding an age group column.
    """
    logger.info("Processing data...")
    
    # Add an age_group column based on the value of age
    df = raw_data.copy()
    df["age_group"] = pd.cut(
        df["age"], 
        bins=config.age_bins, 
        labels=config.age_labels
    )
    
    # Save processed data
    os.makedirs(os.path.dirname(config.output_path), exist_ok=True)
    df.to_csv(config.output_path, index=False)
    logger.info(f"Saved processed data to {config.output_path}")
    
    return df

@asset(deps=[processed_data])
def data_summary(processed_data: pd.DataFrame):
    """
    Generate a summary of the processed data.
    """
    logger.info("Generating data summary...")
    
    # Calculate summary statistics
    summary = {
        "total_rows": len(processed_data),
        "age_stats": processed_data["age"].describe().to_dict(),
        "age_group_counts": processed_data["age_group"].value_counts().to_dict(),
        "cities": processed_data["city"].unique().tolist()
    }
    
    logger.info(f"Summary: {summary}")
    return summary 