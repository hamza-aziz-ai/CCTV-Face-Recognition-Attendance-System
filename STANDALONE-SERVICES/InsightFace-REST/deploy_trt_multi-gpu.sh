#! /bin/bash

# Path to the .env file
ENV_FILE="../standalone-services.env"

if [ -f "$ENV_FILE" ]; then
    # Export variables to the current script's environment
    set -a # Automatically export variables
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a # Stop exporting variables
else
    echo "Environment file $ENV_FILE not found!"
    exit 1
fi


# DEPLOY CONTAINERS

# Create directory to store downloaded models
mkdir -p models

docker build -t "$IMAGE":"$TAG" -f src/Dockerfile_trt src/.

echo "Starting $((N_GPU * NUM_WORKERS)) workers on $N_GPU GPUs ($NUM_WORKERS workers per GPU)";
# shellcheck disable=SC2004
echo "Containers port range: $START_PORT - $(($START_PORT + ($N_GPU) - 1))"


p=0
name=$IMAGE-gpu-mig-trt

for i in "${MIG_GPU[@]}"; do
    # shellcheck disable=SC2089
    device='"device='$i'"';
    # shellcheck disable=SC2004
    port=$((START_PORT + $p));
    container_name=$name-$p;

    # check if container with same name is already running
    if [ "$(docker ps -q -f name="$container_name")" ]; then
        echo --- Container "$container_name" is already running, stopping it;
        docker stop "$container_name";
        docker rm "$container_name";
    fi

    echo --- Starting container "$container_name" with "$device" at port "$port";
    ((p++));
    # shellcheck disable=SC2046
    docker run -p $port:18080 \
        --gpus "$device" \
        -d \
        -e LOG_LEVEL="$LOG_LEVEL" \
        -e USE_NVJPEG="$USING_NVJPEG" \
        -e PYTHONUNBUFFERED=0 \
        -e PORT=18080 \
        -e NUM_WORKERS="$N_WORKERS" \
        -e INFERENCE_BACKEND=trt \
        -e FORCE_FP16="$FP16" \
        -e DET_NAME="$DETECTION_MODEL" \
        -e DET_THRESH="$DETECTION_THRESHOLD" \
        -e REC_NAME="$RECOGNITION_MODEL" \
        -e MASK_DETECTOR="$MASK_DETECTOR_MODEL" \
        -e REC_BATCH_SIZE="$RECOGNITION_BATCH_SIZE" \
        -e DET_BATCH_SIZE="$DETECTION_BATCH_SIZE" \
        -e GA_NAME="$GENDER_AGE_DETECTOR" \
        -e TRITON_URI="$TRITON_URL" \
        -e KEEP_ALL=True \
        -e MAX_SIZE="$MAX_SIZE" \
        -e DEF_RETURN_FACE_DATA="$RETURN_FACE_DATA" \
        -e DEF_EXTRACT_EMBEDDING="$EXTRACT_EMBEDDINGS" \
        -e DEF_EXTRACT_GA="$DETECT_GENDER_AGE" \
        -v $(pwd)/models:/models \
        -v $(pwd)/src:/app \
        --health-cmd='curl -f http://localhost:18080/info || exit 1' \
        --health-interval=1m \
        --health-timeout=10s \
        --health-retries=3 \
        --name="$container_name" \
        "$IMAGE":"$TAG"
done

sleep 30

# Run load balancer for multi-gpu inferencing
echo "Starting Docker NGINX Load Balancer";

docker network create insightface-network

# Connect existing containers to the network
docker network connect insightface-network "$name"-0
docker network connect insightface-network "$name"-1

# shellcheck disable=SC2046
docker run -d \
  --name docker-nginx-insightface \
  --network insightface-network \
  -v $(pwd)/misc/nginx_conf/conf.d:/etc/nginx/conf.d \
  -p 6385:18080 \
  --ulimit nofile=200000:200000 \
  nginx
