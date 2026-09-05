#!/bin/sh
set -e

# Extract version from pyproject.toml
VERSION=$(grep 'version = ' pyproject.toml | sed -E 's/.*version = "([^"]+)".*/\1/')

# Build and tag the Docker image
IMAGE="registry.home/ai-processors/text-processor:$VERSION"

echo "Building image: $IMAGE"
docker build -f Dockerfile -t "$IMAGE" .

echo "Image built: $IMAGE"
