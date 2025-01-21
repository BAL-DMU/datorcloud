#!/usr/bin/env bash

# Exit immediately on errors, treat unset variables as errors, and 
# propagate errors through pipelines.
set -Eeuo pipefail

##
# Pull the MinIO image from Docker Hub on a machine with Internet access
##
echo "Pulling the MinIO Docker image..."
docker pull minio/minio:latest

##
# Save the MinIO image to a tar file
##
echo "Saving the MinIO Docker image to minio.tar..."
docker save -o minio_image.tar minio/minio:latest

# # ----------------------------------------------------------------
# # Transfer the 'minio.tar' file to the offline machine, e.g. using scp, USB, etc.
# # ----------------------------------------------------------------

# ##
# # Load the MinIO image from the tar file on the offline machine
# ##
# echo "Loading the MinIO Docker image from minio.tar..."
# docker load -i minio.tar

# ##
# # (Optional) Tag the image for a private registry
# # Adjust "your-registry.example.com" and "username" to match your setup.
# ##
# echo "Tagging the image for the private registry..."
# docker tag minio/minio:latest your-registry.example.com/username/minio:latest

# ##
# # Log in to the private registry (if not already logged in)
# # docker login your-registry.example.com
# ##

# ##
# # Push the image to the private registry
# ##
# echo "Pushing the image to the private registry..."
# docker push your-registry.example.com/username/minio:latest

echo "Done!"
