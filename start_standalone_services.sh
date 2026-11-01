#!/bin/bash

# DESCRIPTION: This script is used to start the services for facial recognition. The services include InsightFace-REST, Milvus Vector Database, Face Liveness Detection and Confluent Kafka
# Author: Hamza Aziz
# Created: Tuesday, 29 December 2024

# call this script to deploy the project

# Run from this script's folder, so a checkout and a release bundle work alike (D-033). This site's .env and master.env
# are in CONFIG_DIR: the checkout itself by default, the site folder on a deployment host.
cd "$(dirname "$0")" || exit 1
CONFIG_DIR=${CONFIG_DIR:-$(pwd)}
export CONFIG_DIR
# Models and TensorRT engines are this host's data: outside the bundle, so a new release does not rebuild them
[ "$CONFIG_DIR" = "$(pwd)" ] || export INSIGHTFACE_MODELS_DIR=${INSIGHTFACE_MODELS_DIR:-$CONFIG_DIR/insightface-models}

# Load the IP_ADDRESS variable from master.env
. set_configuration.sh

# Per-host overrides (GPU placement, batch sizes) from STANDALONE-SERVICES/hosts/, selected by HOST_PROFILE in .env.
# Nothing read it from .env before, so a run without it exported silently ignored the profile (2026-10-31).
# Only this key is read: .env also holds credentials. An exported HOST_PROFILE still wins.
HOST_PROFILE=${HOST_PROFILE:-$(sed -n 's/^HOST_PROFILE=//p' "$CONFIG_DIR/.env" 2>/dev/null | tr -d "\"'\r" | tail -n 1)}
export HOST_PROFILE
ENV_FILES=(--env-file ../standalone-services.env)
if [ -n "${HOST_PROFILE:-}" ]; then
    [ -f "STANDALONE-SERVICES/hosts/$HOST_PROFILE.env" ] || { echo "Host profile $HOST_PROFILE not found"; exit 1; }
    ENV_FILES+=(--env-file "../hosts/$HOST_PROFILE.env")
    echo "Using host profile: $HOST_PROFILE"
fi
# Last, so this host's IP_ADDRESS (written by set_configuration.sh) wins over the placeholder in standalone-services.env
ENV_FILES+=(--env-file "$CONFIG_DIR/master.env")

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
docker-compose "${ENV_FILES[@]}" up -d
cd ../..

echo

# start the dataset store (DVC remote); its credentials and data folder come from .env
echo "Starting Dataset Store (DVC remote)"
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Dataset-Store
docker-compose --env-file "$CONFIG_DIR/.env" up -d
cd ../..

echo

# start Kafka
echo "Starting Confluent Kafka Service"
# shellcheck disable=SC2164
cd STANDALONE-SERVICES/Confluent-Kafka
docker-compose "${ENV_FILES[@]}" up -d
cd ../..
