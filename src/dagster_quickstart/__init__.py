"""
Dagster-quickstart package for component-oriented workflows.
"""
# Import the definitions from the main file for easier access
from src.dagster_quickstart.definitions import defs

# Explicitly expose the defs object at the module level
__all__ = ['defs'] 