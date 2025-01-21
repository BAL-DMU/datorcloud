# Base image for DuckDB setup
FROM ubuntu:24.10 AS base

# Install dependencies
RUN apt-get update \
    && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    unzip

# Copy the pre-downloaded DuckDB CLI
COPY build/duckdb_cli.zip .
RUN unzip duckdb_cli.zip \
    && rm duckdb_cli.zip \
    && mv duckdb /usr/local/bin/duckdb \
    && chmod +x /usr/local/bin/duckdb

# Create a virtual environment
RUN python3 -m venv /opt/venv

# Activate the virtual environment and install dependencies
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip \
    && pip install \
    duckdb \
    pandas \
    mlcroissant \
    tensorflow-datasets

# Copy the application code
COPY src/ ./src

# Set the working directory
WORKDIR /orx-surgdatahub

# Set the default command to launch DuckDB shell
CMD ["duckdb"]