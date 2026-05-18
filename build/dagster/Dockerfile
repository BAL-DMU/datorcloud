FROM ubuntu:22.04

# Prevent interactive prompts during apt operations
ENV DEBIAN_FRONTEND=noninteractive

# Set up Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

# 1. Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    git \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Set up working directory
WORKDIR /app

# 3. Create and activate a virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 4. Install Dagster and dependencies with better network resilience
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --timeout 300 --retries 10 dagster dagster-webserver

# Install more dependencies in smaller batches for better reliability
RUN pip install --no-cache-dir --timeout 300 --retries 10 dagster-graphql dagster-postgres dagster-docker

# Install data processing libraries separately
RUN pip install --no-cache-dir --timeout 300 --retries 10 pandas numpy

# Install visualization and machine learning libraries
RUN pip install --no-cache-dir --timeout 300 --retries 10 matplotlib scikit-learn

# Install networking libraries
RUN pip install --no-cache-dir --timeout 300 --retries 10 requests httpx dagit

# 5. Add Python package path
ENV PYTHONPATH=/app:/app/src

# 6. Add startup script that uses the existing project structure
RUN echo '#!/bin/bash\n\
echo "Starting Dagster webserver..."\n\
\n\
# Copy code from workspace to app directory if mounted\n\
if [ -d "/app/workspace/src/dagster_quickstart" ]; then\n\
    echo "Found workspace code, copying to /app/src"\n\
    mkdir -p /app/src\n\
    cp -r /app/workspace/src/dagster_quickstart /app/src/\n\
    ls -la /app/src/dagster_quickstart\n\
fi\n\
\n\
# Check if src/dagster_quickstart exists\n\
if [ -d "/app/src/dagster_quickstart" ]; then\n\
    WORKSPACE_PATH="/app/src/dagster_quickstart"\n\
    # Check if there\'s a workspace.yaml file\n\
    if [ -f "${WORKSPACE_PATH}/workspace.yaml" ]; then\n\
        echo "Found workspace.yaml, using file-based workspace"\n\
        cd /app\n\
        # Print debugging information\n\
        echo "Python sys.path:"\n\
        python3 -c "import sys; print(sys.path)"\n\
        echo "Trying to import module:"\n\
        python3 -c "import src.dagster_quickstart; print(dir(src.dagster_quickstart))"\n\
        # Run Dagster\n\
        dagster dev -w ${WORKSPACE_PATH}/workspace.yaml -h 0.0.0.0 -p 3030 --verbose\n\
    else\n\
        # Look for Python modules with Dagster code\n\
        echo "No workspace.yaml found, looking for Python modules"\n\
        MODULES=$(find ${WORKSPACE_PATH} -name "*.py" -type f -exec grep -l "Definitions" {} \\;)\n\
        \n\
        if [ -n "$MODULES" ]; then\n\
            echo "Found Dagster modules:"\n\
            echo "$MODULES"\n\
            \n\
            # Use the first module found\n\
            FIRST_MODULE=$(echo "$MODULES" | head -n 1)\n\
            echo "Loading Dagster definitions from $FIRST_MODULE"\n\
            cd /app\n\
            dagster dev -f "$FIRST_MODULE" -h 0.0.0.0 -p 3030\n\
        else\n\
            echo "No Dagster modules found, creating workspace.yaml"\n\
            cd ${WORKSPACE_PATH}\n\
            echo "load_from:" > workspace.yaml\n\
            echo "  - python_module:" >> workspace.yaml\n\
            echo "      module_name: src.dagster_quickstart" >> workspace.yaml\n\
            cd /app\n\
            dagster dev -w ${WORKSPACE_PATH}/workspace.yaml -h 0.0.0.0 -p 3030\n\
        fi\n\
    fi\n\
else\n\
    # Fallback to a simple example if the expected directory doesn\'t exist\n\
    echo "Warning: /app/src/dagster_quickstart not found, creating a basic example"\n\
    \n\
    # Create the example directories\n\
    mkdir -p /app/src/dagster_quickstart/quickstart\n\
    mkdir -p /app/src/dagster_quickstart/data\n\
    \n\
    # Create sample data file\n\
    echo "id,name,age,city\n1,Alice,28,New York\n2,Bob,35,San Francisco\n3,Charlie,42,Chicago\n4,Diana,31,Los Angeles" > /app/src/dagster_quickstart/data/sample_data.csv\n\
    \n\
    # Create the asset file\n\
    cat > /app/src/dagster_quickstart/quickstart/assets.py << EOF\n\
import pandas as pd\n\
import dagster as dg\n\
\n\
@dg.asset\n\
def processed_data():\n\
    # Read data from the CSV\n\
    df = pd.read_csv("/app/src/dagster_quickstart/data/sample_data.csv")\n\
    \n\
    # Add an age_group column based on the value of age\n\
    df["age_group"] = pd.cut(\n\
        df["age"], bins=[0, 30, 40, 100], labels=["Young", "Middle", "Senior"]\n\
    )\n\
    \n\
    # Save processed data\n\
    df.to_csv("/app/src/dagster_quickstart/data/processed_data.csv", index=False)\n\
    return "Data loaded successfully"\n\
\n\
# Create a job that will materialize the asset\n\
process_data_job = dg.define_asset_job(\n\
    name="process_data_job",\n\
    selection="processed_data"\n\
)\n\
\n\
# Tell Dagster about the assets and jobs that make up the data pipeline\n\
defs = dg.Definitions(\n\
    assets=[processed_data],\n\
    jobs=[process_data_job]\n\
)\n\
EOF\n\
    \n\
    # Create __init__.py to make the directory a Python package\n\
    touch /app/src/dagster_quickstart/quickstart/__init__.py\n\
    touch /app/src/dagster_quickstart/__init__.py\n\
    \n\
    cd /app\n\
    dagster dev -f src/dagster_quickstart/quickstart/assets.py -h 0.0.0.0 -p 3030\n\
fi\n' > /app/start.sh

RUN chmod +x /app/start.sh

# 7. Create a default workspace.yaml file
RUN mkdir -p /app/src/dagster_quickstart && \
    echo 'load_from:' > /app/src/dagster_quickstart/workspace.yaml && \
    echo '  - python_module:' >> /app/src/dagster_quickstart/workspace.yaml && \
    echo '      module_name: src.dagster_quickstart' >> /app/src/dagster_quickstart/workspace.yaml

# 8. Expose the port Dagster runs on
EXPOSE 3030

# 9. Set up entry point
CMD ["/app/start.sh"]

# 10. Add debugging commands
RUN echo "Checking Python path..." && \
    echo $PYTHONPATH && \
    echo "Listing /app/src directory..." && \
    ls -la /app/src && \
    echo "Listing /app/src/dagster_quickstart directory..." && \
    ls -la /app/src/dagster_quickstart