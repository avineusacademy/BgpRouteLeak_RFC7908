#!/bin/bash

# Stop all running containers if any
if [ "$(docker ps -q)" ]; then
  docker stop $(docker ps -q)
else
  echo "No running containers to stop."
fi

# Remove all containers if any
if [ "$(docker ps -aq)" ]; then
  docker rm $(docker ps -aq)
else
  echo "No containers to remove."
fi

