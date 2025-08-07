#!/bin/bash

echo "🖼️ Checking for Docker images to remove..."

# List all image IDs
IMAGE_IDS=$(docker images -q)

if [ -z "$IMAGE_IDS" ]; then
  echo "✅ No Docker images found. Nothing to remove."
else
  echo "Removing all Docker images..."
  docker rmi -f $IMAGE_IDS
  echo "✅ All Docker images removed."
fi

