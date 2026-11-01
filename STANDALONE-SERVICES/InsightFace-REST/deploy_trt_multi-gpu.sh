#! /bin/bash

# Path to the .env file
ENV_FILE="../standalone-services.env"

if [ -f "$ENV_FILE" ]; then
    # Export variables to the current script's environment
    set -a # Automatically export variables
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    # Per-host overrides (GPU placement, batch sizes), selected by HOST_PROFILE in the root .env
    if [ -n "${HOST_PROFILE:-}" ]; then
        # shellcheck disable=SC1090
        source "../hosts/$HOST_PROFILE.env" || { echo "Host profile $HOST_PROFILE not found"; exit 1; }
    fi
    set +a # Stop exporting variables
else
    echo "Environment file $ENV_FILE not found!"
    exit 1
fi


# DEPLOY CONTAINERS

# Git Bash on Windows rewrites mount targets like ":/app" into Windows paths and Docker needs a Windows source path there; both lines are no-ops on Linux
export MSYS_NO_PATHCONV=1
HERE=$(pwd -W 2>/dev/null || pwd)

# Downloaded models and built engines: this folder by default; start_standalone_services.sh points a deployment host
# at its site folder. models.json comes with the release, so it is refreshed there on every start.
MODELS_DIR=${INSIGHTFACE_MODELS_DIR:-models}
mkdir -p "$MODELS_DIR"
[ "$MODELS_DIR" = models ] || cp models/models.json "$MODELS_DIR/models.json"
MODELS_DIR=$(cd "$MODELS_DIR" && (pwd -W 2>/dev/null || pwd))

# The image CI published for this source tree (insightface-image.yml). A deployment bundle sets INSIGHTFACE_IMAGE to its
# digest; in a checkout the tag comes from git. To try uncommitted changes, docker build -t "$INSIGHTFACE_IMAGE" first.
INSIGHTFACE_IMAGE=${INSIGHTFACE_IMAGE:-$IMAGE:$TAG-$(git rev-parse --short=12 HEAD:./src)}
docker image inspect "$INSIGHTFACE_IMAGE" > /dev/null 2>&1 || docker pull "$INSIGHTFACE_IMAGE" || exit 1

echo "Starting ${#INSIGHTFACE_GPUS[@]} containers on GPUs ${INSIGHTFACE_GPUS[*]}, $N_WORKERS worker(s) each";
# shellcheck disable=SC2004
echo "Containers port range: $START_PORT - $(($START_PORT + ${#INSIGHTFACE_GPUS[@]} - 1))"


p=0
# Fixed name: nginx (misc/nginx_conf) and stop_standalone_services.sh address the containers by it
name=insightface-rest-trt

for i in "${INSIGHTFACE_GPUS[@]}"; do
    # shellcheck disable=SC2089
    device='"device='$i'"';
    # shellcheck disable=SC2004
    port=$((START_PORT + $p));
    container_name=$name-$p;

    # Remove a previous container of the same name, running or stopped (restart policies keep stopped ones around)
    docker rm -f "$container_name" 2>/dev/null || true

    echo --- Starting container "$container_name" with "$device" at port "$port";
    ((p++));
    # shellcheck disable=SC2046
    docker run -p $port:18080 \
        --gpus "$device" \
        --restart unless-stopped \
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
        -v "$MODELS_DIR":/models \
        --health-cmd='curl -f http://localhost:18080/info || exit 1' \
        --health-interval=1m \
        --health-timeout=10s \
        --health-retries=3 \
        --name="$container_name" \
        "$INSIGHTFACE_IMAGE"
done

sleep 30

# Run load balancer for multi-gpu inferencing
echo "Starting Docker NGINX Load Balancer";

docker network create insightface-network

# Connect existing containers to the network
for ((n = 0; n < ${#INSIGHTFACE_GPUS[@]}; n++)); do
    docker network connect insightface-network "$name-$n"
done

docker rm -f docker-nginx-insightface 2>/dev/null || true
# shellcheck disable=SC2046
docker run -d \
  --restart unless-stopped \
  --name docker-nginx-insightface \
  --network insightface-network \
  -v "$HERE"/misc/nginx_conf/conf.d:/etc/nginx/conf.d \
  -p 6385:18080 \
  --ulimit nofile=200000:200000 \
  nginx
