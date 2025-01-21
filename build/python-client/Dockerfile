# File: build/python-client/Dockerfile
FROM ubuntu:22.04

# Prevent some interactive prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install Python 3.10, pip, and any system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Optionally ensure "python" points to python3.10
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1

# 2. Copy the requirements file (if you keep it in the project root)
WORKDIR /app
COPY requirements.txt /app/

# 3. Install Python dependencies (including duckdb, minio, etc.)
#    If your requirements.txt includes 'duckdb' and 'minio' or 'boto3', 
#    then you can rely on that. Otherwise, you can explicitly install them below.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 4. Copy your source code into the container
COPY src/ /app/src/

# 5. (Optional) If you want default environment variables baked in, do it here:
# ENV S3_ENDPOINT=http://minio:9000 \
#     S3_USE_SSL=false \
#     S3_REGION=us-east-1 \
#     S3_ACCESS_KEY=minioadmin \
#     S3_SECRET_KEY=minioadmin

# 6. Set the working directory for your scripts
WORKDIR /app/src

# 7. Set a default command or entrypoint
#    You can override this in docker-compose if needed
CMD ["python", "--version"]
