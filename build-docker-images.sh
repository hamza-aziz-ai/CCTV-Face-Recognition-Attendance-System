#!/bin/bash

# shellcheck disable=SC2006

echo "Building docker image for CCTV-Face-Recognition producer-consumer with image name `cctv-face-recognition-producer-consumer:v-beta`"
docker build --tag cctv-face-recognition-producer-consumer:v-beta -f main.Dockerfile .

echo

echo "Building docker image for CCTV-Face-Recognition database-controller with image name `cctv-face-recognition-database-controller:v-beta`"
docker build --tag cctv-face-recognition-database-controller:v-beta -f database-server.Dockerfile .

echo

echo "Building docker image for CCTV-Face-Recognition feedback-controller with image name `cctv-face-recognition-feedback-controller:v-beta`"
docker build --tag cctv-face-recognition-feedback-controller:v-beta -f feedback-server.Dockerfile .

echo

echo "Building docker image for CCTV-Face-Recognition API service with image name `cctv-face-recognition-api:v-beta`"
docker build --tag cctv-face-recognition-api:v-beta -f api.Dockerfile .

echo

echo "Building docker image for CCTV-Face-Recognition display-image-server with image name `cctv-face-recognition-front-face-image-display:v-beta`"
docker build --tag cctv-face-recognition-front-face-image-display:v-beta -f display-image.Dockerfile .

echo

echo "Building docker image for CCTV-Face-Recognition dynamic dataset collector with image name `cctv-face-recognition-dynamic-face-dataset-collector:v-beta`"
docker build --tag cctv-face-recognition-dynamic-face-dataset-collector:v-beta -f dynamic-face-dataset-collector.Dockerfile .

echo

echo "Building docker image for CCTV-Face-Recognition automatic Milvus Vector Database updater with image name `cctv-face-recognition-automate-milvus-update:v-beta`"
docker build --tag cctv-face-recognition-automate-milvus-update:v-beta -f automatic-milvus-db-update.Dockerfile .
