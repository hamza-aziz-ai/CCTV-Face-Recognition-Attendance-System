#!/bin/bash

# Source the get_ip.sh script to import the IP_ADDRESS variable
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
source ./get_ip.sh
CONFIG_DIR=${CONFIG_DIR:-$(pwd)}

# Use the IP_ADDRESS variable
echo "The system's IP address is: $IP_ADDRESS"

# Update this site's master.env (created from the template on first run). The standalone stacks read the IP from it
# too, so no tracked file is changed: a checkout stays clean and a release bundle is never edited.
[ -f "$CONFIG_DIR/master.env" ] || cp master.env.example "$CONFIG_DIR/master.env"
sed -i "/^IP_ADDRESS=/c\IP_ADDRESS=$IP_ADDRESS" "$CONFIG_DIR/master.env"
