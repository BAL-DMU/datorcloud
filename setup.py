from setuptools import setup, find_packages

setup(
    name="datorcloud",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "minio>=7.1.15",
        "duckdb>=1.2.0",
        "pandas>=1.5.3",
        "dagster>=1.4.0"
    ],
)
