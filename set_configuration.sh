#!/bin/bash

# Source the get_ip.sh script to import the IP_ADDRESS variable
source ./get_ip.sh

# Use the IP_ADDRESS variable
echo "The system's IP address is: $IP_ADDRESS"

# Update the master.env file (created from the template on first run)
[ -f master.env ] || cp master.env.example master.env
sed -i "/^IP_ADDRESS=/c\IP_ADDRESS=$IP_ADDRESS" master.env

# Update the secondary.env file
sed -i "/^IP_ADDRESS=/c\IP_ADDRESS=$IP_ADDRESS" STANDALONE-SERVICES/standalone-services.env
