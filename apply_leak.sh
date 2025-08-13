#!/bin/bash

set -e

echo "Running apply_leak.sh with args: $@"
which bash
which sh
ls -l $(dirname "$0")

ROUTER=$1
LEAK_TYPE=$2

if [ -z "$ROUTER" ] || [ -z "$LEAK_TYPE" ]; then
  echo "Usage: $0 <router_name> <leak_type>"
  exit 1
fi

echo "Applying leak '$LEAK_TYPE' on $ROUTER..."

# Get BGP AS dynamically from router config
BGP_AS=$(docker exec "$ROUTER" vtysh -c "show running-config router bgp" | grep "router bgp" | awk '{print $3}')

if [ -z "$BGP_AS" ]; then
  echo "Failed to get BGP AS for $ROUTER"
  exit 2
fi

# Build vtysh commands for leaks
case "$LEAK_TYPE" in
  type1)
    # Example: route-map LEAK1 that matches community 100:100 and sets local-pref 50 on neighbor 192.168.12.1
    read -r -d '' CMDS <<EOF
configure terminal
route-map LEAK1 permit 10
 match community 100:100
 set local-preference 50
exit
router bgp $BGP_AS
 address-family ipv4 unicast
  neighbor 192.168.12.1 route-map LEAK1 out
 exit-address-family
exit
write memory
EOF
    ;;
  type2)
    # Add your type2 leak commands here similarly
    echo "Leak type2 not implemented yet"
    exit 3
    ;;
  *)
    echo "Unknown leak type: $LEAK_TYPE"
    exit 4
    ;;
esac

# Apply commands inside container via vtysh
docker exec -i "$ROUTER" vtysh <<EOF
$CMDS
EOF

echo "Leak '$LEAK_TYPE' applied on $ROUTER."
