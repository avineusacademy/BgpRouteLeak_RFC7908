#!/bin/bash

echo "🌐 Checking for user-defined Docker networks..."

# Get all user-defined network IDs (excluding bridge, host, none)
NETWORK_IDS=$(docker network ls --filter "type=custom" -q)

if [ -z "$NETWORK_IDS" ]; then
  echo "✅ No user-defined Docker networks to remove."
else
  echo "Removing user-defined Docker networks..."
  docker network rm $NETWORK_IDS
  echo "✅ All user-defined Docker networks removed."
fi

