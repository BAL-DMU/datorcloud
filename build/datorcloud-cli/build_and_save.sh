#!/usr/bin/env bash

# -----------------------------------------------------------------
# build_datorcloud_cli.sh
# A script to build and save the DatorCloud CLI Docker image
# from an Ubuntu 22.04 + Python 3.10 Dockerfile.
# -----------------------------------------------------------------

# 1) Name/tag for your Docker image
IMAGE_NAME="datorcloud-cli"
IMAGE_TAG="latest"

# 2) Path to the Dockerfile (relative to the project root)
DOCKERFILE_PATH="build/datorcloud-cli/Dockerfile"

# 3) Output tar file location
OUTPUT_TAR="docker/datorcloud_cli_image.tar"

# 4) Build the image
echo "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG} ..."
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f "${DOCKERFILE_PATH}" .

# 5) Create the 'docker' directory if it doesn't exist
mkdir -p docker

# 6) Save the built image as a tar archive
echo "Saving Docker image to ${OUTPUT_TAR} ..."
docker save -o "${OUTPUT_TAR}" "${IMAGE_NAME}:${IMAGE_TAG}"

echo "Done! The image ${IMAGE_NAME}:${IMAGE_TAG} has been saved to ${OUTPUT_TAR}."
