#!/bin/bash

set -e

ROUTER="r1"
echo "Applying community tagging configuration to $ROUTER..."

echo "Docker containers running:"
docker ps --format '{{.Names}}'

echo "Getting BGP AS from $ROUTER..."
BGP_AS=$(docker exec "$ROUTER" vtysh -c "show running-config" | grep "^router bgp " | awk '{print $3}')

if [ -z "$BGP_AS" ]; then
  echo "Failed to get BGP AS for $ROUTER"
  exit 1
fi

echo "BGP AS is $BGP_AS"

CMDS=$(cat <<EOF
configure terminal
route-map TAG_COMM permit 10
 set community 100:100
exit
router bgp $BGP_AS
 address-family ipv4 unicast
  network 1.1.1.1/32 route-map TAG_COMM
  neighbor 20.20.1.3 send-community
exit-address-family
exit
do write memory
EOF
)

echo "Applying BGP config commands..."
docker exec -i "$ROUTER" vtysh <<EOF
$CMDS
EOF

echo "Configuration applied to $ROUTER (AS$BGP_AS) to tag 1.1.1.1/32 with community 100:100 and send community to R2."
