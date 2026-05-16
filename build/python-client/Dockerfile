# File: build/python-client/Dockerfile
FROM ubuntu:22.04

# Prevent interactive prompts during apt operations
ENV DEBIAN_FRONTEND=noninteractive

# Define DuckDB version and installation paths
# Note: We explicitly use linux_amd64_gcc4 to match DuckDB's expected path
ENV DUCKDB_VERSION="v1.2.0"
ENV DUCKDB_EXTENSION_PATH="/root/.duckdb/extensions/${DUCKDB_VERSION}/linux_amd64_gcc4/"

# 1. Install system dependencies
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
    unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Install DuckDB CLI 1.2.0
RUN curl --fail --location --progress-bar \
    --output duckdb_cli-linux-amd64.zip \
    https://github.com/duckdb/duckdb/releases/download/v1.2.0/duckdb_cli-linux-amd64.zip \
    && unzip duckdb_cli-linux-amd64.zip \
    && mv duckdb /usr/local/bin/ \
    && chmod +x /usr/local/bin/duckdb \
    && rm duckdb_cli-linux-amd64.zip

# 3. Create DuckDB extension directory and install HTTPFS extension
# Note: We create the directory with explicit permissions and ownership
RUN mkdir -p ${DUCKDB_EXTENSION_PATH} \
    && chmod 755 $(dirname ${DUCKDB_EXTENSION_PATH}) \
    && curl -L --fail \
    -o /tmp/httpfs.duckdb_extension.gz \
    "https://extensions.duckdb.org/${DUCKDB_VERSION}/linux_amd64_gcc4/httpfs.duckdb_extension.gz" \
    && gunzip /tmp/httpfs.duckdb_extension.gz \
    && mv /tmp/httpfs.duckdb_extension ${DUCKDB_EXTENSION_PATH}httpfs.duckdb_extension \
    && chmod 755 ${DUCKDB_EXTENSION_PATH}httpfs.duckdb_extension \
    && echo '{"name": "httpfs", "version": "1.2.0"}' > ${DUCKDB_EXTENSION_PATH}httpfs.duckdb_extension.info \
    && chmod 644 ${DUCKDB_EXTENSION_PATH}httpfs.duckdb_extension.info

# 4. Install Miniconda
RUN wget --progress=bar:force:noscroll \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    -O /tmp/miniconda.sh \
    && /bin/bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh

# 5. Ensure conda is in PATH
ENV PATH="/opt/conda/bin:${PATH}"

# 6. Create a minimal environment and install Python 3.10 + data-science libraries
RUN conda install -y \
    python=3.10 \
    pip \
    numpy \
    pandas \
    scikit-learn \
    matplotlib \
    && conda clean -ya

# 7. Install DuckDB 1.2.0 Python package
RUN pip install --no-cache-dir duckdb==1.2.0

# 8. Verify DuckDB installation and extensions
RUN python -c "import duckdb; print(f'DuckDB version: {duckdb.__version__}')" \
    && ls -la ${DUCKDB_EXTENSION_PATH} \
    && echo "DuckDB extension directory contents verified"

# Rest of your Dockerfile remains the same...
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY datorcloud/ /app/datorcloud/
COPY pyproject.toml setup.py /app/
RUN pip install --no-cache-dir -e .

CMD ["python", "--version"]