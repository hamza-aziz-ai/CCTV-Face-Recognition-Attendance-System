#!/bin/bash

# Description: This script is used delete all existing mfr containers
# Author: Anubhav Patrick
# Modification: Hamza Aziz
# Created: Thur September 14 2023
# Modified: Sunday, 29 December 2024

# Run from this script's folder, so a checkout and a release bundle work alike (D-033). This site's .env and master.env
# are in CONFIG_DIR: the checkout itself by default, the site folder on a deployment host.
cd "$(dirname "$0")" || exit 1
CONFIG_DIR=${CONFIG_DIR:-$(pwd)}
export CONFIG_DIR

NETWORK_NAME="insightface-network"

# check if insightface-rest-trt-0 containers exists
if [ "$(docker ps -a -q -f name=insightface-rest-trt-0)" ]; then
    # cleanup
    echo "insightface-rest-trt-0 container exists, stop and remove it"
    # Disconnect from network
    docker network disconnect $NETWORK_NAME insightface-rest-trt-0
    docker stop insightface-rest-trt-0
    docker rm -f insightface-rest-trt-0
fi

echo

# check if insightface-rest-trt-1 containers exists
if [ "$(docker ps -a -q -f name=insightface-rest-trt-1)" ]; then
    # cleanup
    echo "insightface-rest-trt-1 container exists, stop and remove it"
    # Disconnect from network
    docker network disconnect $NETWORK_NAME insightface-rest-trt-1
    docker stop insightface-rest-trt-1
    docker rm -f insightface-rest-trt-1
fi

echo

# check if docker-nginx containers exists
if [ "$(docker ps -a -q -f name=docker-nginx-insightface)" ]; then
    # cleanup
    echo "docker-nginx-insightface container exists, stop and remove it"
    docker stop docker-nginx-insightface
    docker rm -f docker-nginx-insightface
fi

echo

# check if the network exists, then remove it
if [ "$(docker network ls -q -f name=$NETWORK_NAME)" ]; then
    echo "Network $NETWORK_NAME exists, removing it"
    docker network rm $NETWORK_NAME
fi

echo

# Face Liveness Detection containers cleanup
# shellcheck disable=SC2164
# cd STANDALONE-SERVICES/Face-Liveness-Detection
# docker-compose --env-file ../standalone-services.env -f docker-compose-multi-gpu.yml down
# shellcheck disable=SC2103
# cd ../..

echo

# Kafka containers cleanup
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Confluent-Kafka
# shutdown kafka stack
echo "shutdown kafka stack"
docker-compose --env-file ../standalone-services.env down
cd ../..

echo

# Milvus containers cleanup
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Milvus-Vector-Database
# shutdown kafka stack
echo "shutdown Milvus stack"
docker-compose --env-file ../standalone-services.env down
cd ../..

# Dataset store (DVC remote) cleanup; its data folder (DATASET_STORE_DIR) is kept
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Dataset-Store
echo "shutdown Dataset Store"
docker-compose --env-file "$CONFIG_DIR/.env" down
cd ../..
