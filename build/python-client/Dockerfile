# File: build/python-client/Dockerfile
FROM ubuntu:22.04

# Prevent interactive prompts during apt operations
ENV DEBIAN_FRONTEND=noninteractive

# Define DuckDB extensions path
ENV DUCKDB_VERSION="v0.8.1"
ENV DUCKDB_EXTENSION_PATH="/root/.duckdb/extensions/${DUCKDB_VERSION}/linux_amd64_gcc4/"

# 1. Install system dependencies needed for Miniconda, DuckDB extension installation, and vim
RUN apt-get update && apt-get install -y \
    wget \
    bzip2 \
    ca-certificates \
    gzip \
    vim \
    libcurl4-openssl-dev \
    iputils-ping \
    curl \
    file \
    gdb \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Install Miniconda
RUN wget --progress=bar:force:noscroll \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    -O /tmp/miniconda.sh \
    && /bin/bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh

# 3. Ensure conda is in PATH
ENV PATH="/opt/conda/bin:${PATH}"

# 4. Create a minimal environment and install Python 3.10 + data-science libraries
RUN conda install -y \
    python=3.10 \
    pip \
    numpy \
    pandas \
    scikit-learn \
    matplotlib \
    && conda clean -ya

# 5. Install the latest DuckDB version and HTTPFS extension
RUN pip install --no-cache-dir --upgrade duckdb
RUN curl -L --fail -o /tmp/httpfs.duckdb_extension.gz http://extensions.duckdb.org/${DUCKDB_VERSION}/linux_amd64_gcc4/httpfs.duckdb_extension.gz \
    && gunzip /tmp/httpfs.duckdb_extension.gz \
    && mkdir -p ${DUCKDB_EXTENSION_PATH} \
    && mv /tmp/httpfs.duckdb_extension ${DUCKDB_EXTENSION_PATH}httpfs.duckdb_extension \
    && chmod 644 ${DUCKDB_EXTENSION_PATH}httpfs.duckdb_extension

# 6. Set working directory
WORKDIR /app

# 7. Copy requirements and source code
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ /app/src/

# 8. Rename conflicting minio.py file if it exists
RUN if [ -f /app/src/orx-surghub/minio.py ]; then \
        mv /app/src/orx-surghub/minio.py /app/src/orx-surghub/minio_local.py; \
    fi

# 9. Set default command
CMD ["python", "--version"]