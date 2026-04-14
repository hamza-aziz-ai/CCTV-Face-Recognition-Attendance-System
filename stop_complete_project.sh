#!/bin/bash

# Description: This script is used delete all existing mfr containers
# Author: Anubhav Patrick
# Modification: Hamza Aziz
# Created: Thur September 14 2023
# Modified: Tuesday, 4 June 2024

. stop_standalone_services.sh

echo

# Main program, Redis, Database and Feedback Controller, API Service and Face Liveness Detection Containers cleanup
echo "main program, redis, database and feedback controller, api service and face liveness detection containers"
docker-compose -f docker-compose-main.yml down --remove-orphans
