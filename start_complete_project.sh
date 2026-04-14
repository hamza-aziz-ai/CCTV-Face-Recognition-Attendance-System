#!/bin/bash

# Description: This script is used to deploy the project
# Author: Anubhav Patrick
# Modification: Hamza Aziz
# Created: Thur September 14 2023
# Modified: Tuesday, 4 June 2024

# make healthcheck scripts executable
# shellcheck disable=SC2046
chmod 777 $(pwd)/src/database_server/healthcheck_db_controller.sh
# shellcheck disable=SC2046
chmod 777 $(pwd)/src/feedback_server/healthcheck_feedback_controller.sh
# shellcheck disable=SC2046
chmod 777 $(pwd)/src/api/healthcheck_api.sh
# shellcheck disable=SC2046
chmod 777 $(pwd)/STANDALONE-SERVICES/Face-Liveness-Detection/healthcheck_face_liveness.sh
# shellcheck disable=SC2046
chmod 777 $(pwd)/src/fetch_face_image_server/healthcheck_display_image_server.sh

# deploy the core modules for the project
. start_standalone_services.sh

echo

# start main program, redis, database and feedback controller, api service and face liveness detection
echo "start main program, redis, database and feedback controller, api service and face liveness detection"
docker-compose -f docker-compose-main.yml up -d
