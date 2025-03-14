#!/usr/bin/env bash
# build_and_save.sh

# Stop the script if any command fails (-e), treat unset variables as errors (-u),
# and propagate errors through pipelines (-o pipefail).
set -Eeuo pipefail

# Customize this with your Docker Hub username
USERNAME="jagh1729"

# Name and tag for the Docker image
# IMAGE_NAME="${USERNAME}/duckdb:latest"
IMAGE_NAME="${USERNAME}/duckdb:v1.2.1"

echo "Building the Docker image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

echo "Saving the Docker image to duckdb_image.tar..."
docker save -o duckdb_image.tar "$IMAGE_NAME"

echo "Pushing the Docker image to Docker Hub..."
# Make sure you are already logged into Docker Hub via:
#    docker login
docker push "$IMAGE_NAME"

echo "Build, save, and push completed successfully."
