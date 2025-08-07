#!/bin/bash

echo "🔽 Stopping all running containers..."
if [ "$(docker ps -q)" ]; then
  docker stop $(docker ps -q)
else
  echo "✅ No running containers to stop."
fi

echo "🗑️ Removing all containers..."
if [ "$(docker ps -aq)" ]; then
  docker rm $(docker ps -aq)
else
  echo "✅ No containers to remove."
fi

echo "🖼️ Removing all Docker images..."
if [ "$(docker images -q)" ]; then
  docker rmi -f $(docker images -q)
else
  echo "✅ No images to remove."
fi

echo "🌐 Removing all user-defined Docker networks..."
# Exclude default networks: bridge, host, none
USER_NETWORKS=$(docker network ls --filter "type=custom" -q)
if [ "$USER_NETWORKS" ]; then
  docker network rm $USER_NETWORKS
else
  echo "✅ No user-defined networks to remove."
fi

echo "✅ Docker cleanup completed."

