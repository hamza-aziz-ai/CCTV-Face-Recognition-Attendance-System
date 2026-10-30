#!/bin/bash

# Source the get_ip.sh script to import the IP_ADDRESS variable
source ./get_ip.sh

# Load host IPs (ABESIT_HOST_IP, GLBITM_HOST_IP) from the git-ignored .env
# shellcheck disable=SC1091
[ -f .env ] && . ./.env

# Use the IP_ADDRESS variable
echo "The system's IP address is: $IP_ADDRESS"


# Conditionally set the IP_ADDRESS based on the INSTITUTE value
if [ "$IP_ADDRESS" == "$ABESIT_HOST_IP" ]; then
    export INSTITUTE="ABESIT"
elif [ "$IP_ADDRESS" == "$GLBITM_HOST_IP" ]; then
    export INSTITUTE="GLBITM"
else
    export INSTITUTE="ABESIT"
fi


# Update the master.env file (created from the template on first run)
[ -f master.env ] || cp master.env.example master.env
sed -i "/^IP_ADDRESS=/c\IP_ADDRESS=$IP_ADDRESS" master.env
sed -i "/^INSTITUTE=/c\INSTITUTE=$INSTITUTE" master.env

# Update the secondary.env file
sed -i "/^IP_ADDRESS=/c\IP_ADDRESS=$IP_ADDRESS" STANDALONE-SERVICES/standalone-services.env
sed -i "/^INSTITUTE=/c\INSTITUTE=$INSTITUTE" STANDALONE-SERVICES/standalone-services.env
