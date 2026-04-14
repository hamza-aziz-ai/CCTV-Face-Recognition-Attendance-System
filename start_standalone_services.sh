#!/bin/bash

# DESCRIPTION: This script is used to start the services for facial recognition. The services include InsightFace-REST, Milvus Vector Database, Face Liveness Detection and Confluent Kafka
# Author: Hamza Aziz
# Created: Tuesday, 29 December 2024

# call this script to deploy the project

# Load the INSTITUTE and IP_ADDRESS variable from master.env
. set_configuration.sh

# start InsightFace-REST container
echo "Starting InsightFace-REST API Service"
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/InsightFace-REST
./deploy_trt_multi-gpu.sh
# shellcheck disable=SC2103
cd ../..

echo

# start face liveness detection service
# echo "Starting Face Liveness Detection Service"
# shellcheck disable=SC2164
# cd STANDALONE-SERVICES/Face-Liveness-Detection
# docker-compose --env-file ../standalone-services.env -f docker-compose-multi-gpu.yml up -d
# cd ../..

# start milvus similarity search container
echo "Starting Milvus Vector Database Service"
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Milvus-Vector-Database
docker-compose --env-file ../standalone-services.env up -d
cd ../..

echo

# start Kafka
echo "Starting Confluent Kafka Service"
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Confluent-Kafka
docker-compose --env-file ../standalone-services.env up -d
cd ../..
