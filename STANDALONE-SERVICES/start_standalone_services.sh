#!/bin/bash

# DESCRIPTION: This script is used to start the services for facial recognition. The services include InsightFace-REST, Milvus Vector Database, Face Liveness Detection and Confluent Kafka
# Author: Hamza Aziz
# Created: Tuesday, 29 December 2024

# call this script to deploy the project

# Load the INSTITUTE variable from master.env
source ../master.env
# Load host IPs (ABESIT_HOST_IP, GLBITM_HOST_IP) from the git-ignored .env
# shellcheck disable=SC1091
[ -f ../.env ] && . ../.env

# Conditionally set the IP_ADDRESS based on the INSTITUTE value
if [ "$INSTITUTE" == "ABESIT" ]; then
    export IP_ADDRESS="$ABESIT_HOST_IP"
elif [ "$INSTITUTE" == "GLBITM" ]; then
    export IP_ADDRESS="$GLBITM_HOST_IP"
else
    echo "Unknown INSTITUTE value: $INSTITUTE"
    exit 1
fi

# Update the standalone-services.env file
sed -i "/^IP_ADDRESS=/c\IP_ADDRESS=$IP_ADDRESS" standalone-services.env


# start InsightFace-REST container
echo "Starting InsightFace-REST API Service"
# shellcheck disable=SC2164
cd InsightFace-REST
./deploy_trt_multi-gpu.sh
# shellcheck disable=SC2103
cd ..

echo

# start face liveness detection service
# echo "Starting Face Liveness Detection Service"
# shellcheck disable=SC2164
# cd Face-Liveness-Detection
# docker-compose --env-file ../standalone-services.env -f docker-compose-multi-gpu.yml up -d
# cd ..

# start milvus similarity search container
echo "Starting Milvus Vector Database Service"
# shellcheck disable=SC2164
cd Milvus-Vector-Database
docker-compose --env-file ../standalone-services.env up -d
cd ..

echo

# start Kafka
echo "Starting Confluent Kafka Service"
# shellcheck disable=SC2164
cd Confluent-Kafka
docker-compose --env-file ../standalone-services.env up -d
cd ..
