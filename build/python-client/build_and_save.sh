#!/usr/bin/env bash

# -----------------------------------------------------------------
# build_python_image.sh
# A script to build and save the Python service Docker image
# from an Ubuntu 22.04 + Python 3.10 Dockerfile.
# -----------------------------------------------------------------

# 1) Name/tag for your Docker image
# IMAGE_NAME="my-python-service"
IMAGE_NAME="dms-python-service"
IMAGE_TAG="latest"

# 2) Path to the Dockerfile (relative to the project root)
DOCKERFILE_PATH="build/python-client/Dockerfile"
# DOCKERFILE_PATH="Dockerfile"

# 3) Output tar file location
OUTPUT_TAR="docker/python_image.tar"
# OUTPUT_TAR="python_image.tar"

# 4) Build the image
echo "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG} ..."
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f "${DOCKERFILE_PATH}" .

# 5) Create the 'docker' directory if it doesn't exist
mkdir -p docker

# 6) Save the built image as a tar archive
echo "Saving Docker image to ${OUTPUT_TAR} ..."
docker save -o "${OUTPUT_TAR}" "${IMAGE_NAME}:${IMAGE_TAG}"

echo "Done! The image ${IMAGE_NAME}:${IMAGE_TAG} has been saved to ${OUTPUT_TAR}."
