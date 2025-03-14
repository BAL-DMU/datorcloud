FROM ubuntu:latest

# Install dependencies
# RUN apt-get update && apt-get install -y unzip xdg-utils lynx www-browser
# RUN apt-get update && apt-get install -y unzip xdg-utils www-browser
RUN apt-get update && apt-get install -y unzip lynx xdg-utils net-tools

# Copy the pre-downloaded CLI file
COPY duckdb_cli-linux-amd64.zip /tmp/
# COPY duckdb_cli-linux-amd64-v1.2.1.zip /tmp/

RUN unzip /tmp/duckdb_cli-linux-amd64.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/duckdb && \
    rm /tmp/duckdb_cli-linux-amd64.zip

# Set entrypoint
ENTRYPOINT ["duckdb"]


# # Base image for DuckDB setup
# FROM ubuntu:24.10 AS base

# # Install dependencies
# RUN apt-get update && apt-get install -y \
#     python3 \
#     python3-pip \
#     python3-venv \
#     unzip \
#     wget && \
#     rm -rf /var/lib/apt/lists/*

# # Copy or download the pre-downloaded DuckDB CLI
# #COPY ../../build/duckdb_cli-linux-amd64.zip /tmp/duckdb_cli.zip
# # Alternatively, download directly (useful if copying is unavailable)
# RUN wget -O /tmp/duckdb_cli.zip https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip

# RUN unzip /tmp/duckdb_cli.zip -d /usr/local/bin/ && \
#     rm /tmp/duckdb_cli.zip && \
#     chmod +x /usr/local/bin/duckdb

# # Create a virtual environment
# RUN python3 -m venv /opt/venv

# # Activate the virtual environment and install Python dependencies
# ENV PATH="/opt/venv/bin:$PATH"
# RUN pip install --upgrade pip && \
#     pip install \
#     duckdb \
#     pandas \
#     mlcroissant \
#     tensorflow-datasets

# # Copy the application code (ensure src directory exists)
# COPY src/ /orx-surgdatahub/src

# # Set the working directory
# WORKDIR /orx-surgdatahub

# # Set the default command to launch DuckDB shell
# CMD ["duckdb"]
