# Base image for DuckDB setup
FROM ubuntu:24.10 AS base
ARG DUCKDB_VERSION=v1.0.0

# Install dependencies and download the DuckDB CLI
RUN apt-get update \
    && apt-get install -y curl unzip python3 python3-pip python3-venv git \
    && curl -L -o duckdb_cli.zip "https://github.com/duckdb/duckdb/releases/download/${DUCKDB_VERSION}/duckdb_cli-linux-amd64.zip" \
    && unzip duckdb_cli.zip \
    && rm duckdb_cli.zip \
    && mv duckdb /usr/local/bin/duckdb

# Create a virtual environment
RUN python3 -m venv /opt/venv

# Activate the virtual environment and install dependencies
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip
RUN pip install duckdb pandas mlcroissant GitPython tensorflow-datasets

# Copy the application code
COPY src/ ./src

# Set the default command to launch DuckDB shell
CMD ["duckdb"]

# Set the working directory
WORKDIR /orx-surghub
