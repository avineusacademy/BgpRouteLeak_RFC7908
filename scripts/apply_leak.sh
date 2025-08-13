#!/bin/bash

set -e

ROUTER=$1
LEAK_TYPE=$2

if [ -z "$ROUTER" ] || [ -z "$LEAK_TYPE" ]; then
  echo "[ERROR] Usage: $0 <router_name> <leak_type>"
  exit 1
fi

ROUTER=$(echo "$ROUTER" | xargs)
ROUTER_UPPER=$(echo "$ROUTER" | tr '[:lower:]' '[:upper:]')

if [ "$LEAK_TYPE" != "type1" ]; then
  echo "[ERROR] Leak type '$LEAK_TYPE' not implemented"
  exit 2
fi

if [ "$ROUTER_UPPER" != "R2" ]; then
  echo "[ERROR] Type 1 leak must be applied on router R2"
  exit 3
fi

BGP_AS=$(docker exec "$ROUTER" vtysh -c "show running-config" | grep "^router bgp" | awk '{print $3}')

if [ -z "$BGP_AS" ]; then
  echo "[ERROR] Failed to retrieve BGP AS number for $ROUTER"
  exit 4
fi

echo "[INFO] Applying leak 'type1' on router '$ROUTER' with BGP AS $BGP_AS..."

docker exec -i "$ROUTER" vtysh <<EOF
configure terminal
bgp community-list standard LEAK_COMM permit 100:100
route-map LEAK1 permit 10
 match community LEAK_COMM
 set local-preference 50
exit
router bgp $BGP_AS
 address-family ipv4 unicast
  neighbor 30.30.1.3 send-community
  neighbor 20.20.1.2 send-community
  neighbor 30.30.1.3 route-map LEAK1 out
 exit-address-family
exit
do write memory
EOF

echo "[SUCCESS] Leak 'type1' applied on router '$ROUTER'."
