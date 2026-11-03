"""
This module contains the default parameters used by the app
"""
from dotenv import load_dotenv
import os
import re
import sys


########################################################################################################################
# Project Configuration
########################################################################################################################
load_dotenv("master.env")
IP_ADDRESS = os.getenv("IP_ADDRESS")

# The client this stack serves (D-036). Required: without it the stack could read or write another client's data
CLIENT_ID = os.getenv("CLIENT_ID", "")
if not re.fullmatch(r"[a-z][a-z0-9]{2,29}", CLIENT_ID):
    sys.exit(f"CLIENT_ID in master.env must be 3 to 30 lowercase letters or digits, starting with a letter; got {CLIENT_ID!r}")
# The owner's site keeps the names it had before D-036
OWNER_CLIENT_ID = "owner"


def client_name(owner_name):
    """This client's name for a database. IDs hold no underscore, so a prefixed name never equals another client's."""
    return owner_name if CLIENT_ID == OWNER_CLIENT_ID else f"{CLIENT_ID}_{owner_name.lower()}"


# Each client logs in to the shared services with its own accounts, made by deploy/provision.py (D-037). Until the
# owner's cutover (step 3c), LEGACY_SHARED_SERVICES=1 in master.env keeps the owner's site as it was: the admin logins,
# no Milvus or Kafka login, unprefixed topics, and databases and topics created at start. Only the owner may set it.
LEGACY_SHARED_SERVICES = os.getenv("LEGACY_SHARED_SERVICES") == "1"
if LEGACY_SHARED_SERVICES and CLIENT_ID != OWNER_CLIENT_ID:
    sys.exit("LEGACY_SHARED_SERVICES=1 is for the owner's site only, until its step 3c cutover")


def login(key):
    """A login value from the site .env; missing means the client was never provisioned, so stop rather than guess."""
    value = os.getenv(key, "")
    if not value:
        sys.exit(f"{key} is not set: run deploy/provision.py {CLIENT_ID} and pass its site .env to this service")
    return value


def postgres_login():
    if LEGACY_SHARED_SERVICES:
        return os.getenv("POSTGRES_USER"), os.getenv("POSTGRES_PASSWORD")
    return login("PG_APP_USER"), login("PG_APP_PASSWORD")


def milvus_login():
    """(user, password); empty for the legacy owner, whose Milvus has no authentication yet."""
    return ("", "") if LEGACY_SHARED_SERVICES else (login("MILVUS_APP_USER"), login("MILVUS_APP_PASSWORD"))


def kafka_login():
    """Extra Kafka client settings: SCRAM on 9092 for every client, nothing for the legacy owner."""
    if LEGACY_SHARED_SERVICES:
        return {}
    return {"security.protocol": "SASL_PLAINTEXT", "sasl.mechanism": "SCRAM-SHA-512",
            "sasl.username": login("KAFKA_APP_USER"), "sasl.password": login("KAFKA_APP_PASSWORD")}



CAMERA_CONFIGURATION_FILE = "src/Camera-Configuration/camera_configuration.json"

# Set video frame height and width
FRAME_HEIGHT = 360  # 720 #576
FRAME_WIDTH = 640  # 1280 #1024
# Desirable frame size (or frame area)
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT
########################################################################################################################

########################################################################################################################
# Parameters specific to Project Paths
########################################################################################################################
FACIAL_RECOGNITION_DATASET_PATH = "FACIAL-RECOGNITION-DATASET"
DYNAMIC_DATASET_PATH = "DYNAMIC-FACIAL-RECOGNITION-DATASET"
FACIAL_RECOGNITION_EMBEDDINGS_PATH = f"{FACIAL_RECOGNITION_DATASET_PATH}/FACE_EMBEDDINGS"
DYNAMIC_DATASET_EMBEDDINGS_PATH = f"{DYNAMIC_DATASET_PATH}/FACE_EMBEDDINGS"
DISPLAY_FACE_IMAGE_PATH = "DISPLAY-FACE-DATASET"
FACE_LANDMARKS_PATH = "FACE-LANDMARKS"
LOGS_FOLDER = "logs"
MULTICAM_SERVER_LOGGER = "multicam_server"
DATABASE_SERVER_LOGGER = "database_server"
API_LOGGER = "api"
FEEDBACK_LOGGER = "feedback_server"
DYNAMIC_FACE_DATA_COLLECTOR_LOGGER = "dynamic_face_data_collector"
########################################################################################################################


########################################################################################################################
# Parameters specific to Cameras, Livestreams and Buffers
########################################################################################################################
# Frame Rate Factor to drop the frames not needed to process
FRAME_RATE_FACTOR = 1

# Decide whether to resize the process for real-time performance
RESIZE_FRAME = True

# Decide whether to crop ROI from camera feed
CROP_ROI = True

# Video decoder for camera streams, from master.env: cpu (OpenCV, the original path), gpu (NVDEC through FFmpeg, which
# also scales frames down on the GPU), or auto (gpu, falling back to cpu for a stream the GPU cannot open). See src/util/video_source.py
VIDEO_DECODE = os.getenv("VIDEO_DECODE", "auto").lower()

# set BATCH_SIZE for face detection
BATCH_SIZE = 32  # frames per InsightFace request; lower it on a small GPU, 8 for CPU

# buffer size for video streaming to minimize inconsistent network conditions
LIVE_STREAM_BUFFER_SIZE = 4096

# buffer size for frames on which face recognition will be performed
LIVE_STREAM_BUFFER_PURGE_SIZE = 256

# IP Camera Details
CAM_USERNAME = os.environ.get("CAM_USERNAME")
CAM_PASSWORD = os.environ.get("CAM_PASSWORD")
CAM_PORT = os.environ.get("CAM_PORT")
STREAM_ENDPOINT = os.environ.get("STREAM_ENDPOINT")

# Set wait duration for IP cam re initialization if we are not able to initialize the cam
IP_CAM_REINIT_WAIT_DURATION = 30  # seconds

# Boolean flag to indicate whether to detect darkness in live stream
DARKNESS_DETECTION = True

# Maximum buffer size for low light intensity detection buffer
LOW_LIGHT_INTENSITY_DETECTION_BUFFER_SIZE = 100

# Majority size to decide whether it is getting dark
MAXIMUM_DARK_FRAMES = 80

# How often a dark camera repeats its alert; below STATUS_THRESHOLD, so the display keeps showing it
LIGHTING_ALERT_SECONDS = 30
########################################################################################################################


########################################################################################################################
# Parameters specific to InsightFace-REST face detection
########################################################################################################################
# InsightFace-REST host; an edge node such as the Jetson sets INSIGHTFACE_HOST in master.env to use its own, while the shared services stay on IP_ADDRESS
INSIGHTFACE_HOST = os.getenv("INSIGHTFACE_HOST") or f"http://{IP_ADDRESS}"

# How frames travel to InsightFace-REST, from master.env: jpeg (base64 JPEG in JSON, the original) or bmp (uncompressed, in
# msgpack: less CPU on both ends, about 15x the bytes, so only for InsightFace on the same machine)
FRAME_TRANSPORT = os.getenv("FRAME_TRANSPORT", "jpeg").lower()

# InsightFace-REST port
INSIGHTFACE_PORT = "6385"  # the nginx load balancer in front of the InsightFace-REST containers

# Threaded GPU Flag
THREAD_FLAG = True
# Multi-Process GPU Flag
MULTIPROCESSING_FLAG = False

# Number of threads to be used for face recognition
NUMBER_OF_THREADS = 4

# Number of processes to be used for face recognition
NUMBER_OF_PROCESSES = 2
########################################################################################################################

########################################################################################################################
# Parameters specific to Face-Liveness-Detection
########################################################################################################################
# Face-Liveness-Detection host
FACE_LIVENESS_DETECTION_HOST = f"http://{IP_ADDRESS}"

# Face-Liveness-Detection port
FACE_LIVENESS_DETECTION_PORT = 6386

# Boolean flag to indicate whether to enable face liveness detection
ENABLE_FACE_LIVENESS_DETECTION = False
########################################################################################################################


########################################################################################################################
# Parameters specific to Milvus Vector Database
########################################################################################################################
# Milvus host
MILVUS_HOST = IP_ADDRESS

# Milvus port
MILVUS_PORT = "19530"

# Milvus database holding this client's collections; the names inside are the same for every client
MILVUS_DATABASE = client_name("default")

# Vector metric type and index type
METRIC_TYPE = "COSINE"
INDEX_TYPE = "GPU_IVF_FLAT"

# Threshold
FACE_MATCHING_TOLERANCE = 0.5 if METRIC_TYPE == "COSINE" else 0.9    # For L2 Metric Type

# Milvus collection name
# MILVUS_COLLECTION_NAME = "TEST_COLLECTION"
MILVUS_COLLECTION_NAME = f"FACE_DATA_COLLECTION_FOR_{METRIC_TYPE}"
########################################################################################################################


########################################################################################################################
# Parameters specific to dynamic facial dataset collection
########################################################################################################################
# Milvus staging collection name for face recognition fallback
MILVUS_STAGING_COLLECTION_NAME = f"FACE_DATA_STAGING_COLLECTION_FOR_{METRIC_TYPE}"

# Boolean flag to indicate whether to do staging
STAGING = True

# Boolean flag to indicate to collect facial dataset at runtime
SAVE_FACE = True

# Threshold value for distance between two eye landmarks to decide whether the face is large enough to save
PUPIL_DISTANCE_THRESHOLD = 28    # px
ENROLMENT_MIN_CONFIDENCE = 0.7    # lowest face detection confidence accepted for an enrolment photo
# Enrolment photo checks (src/util/enrolment_checks.py). The pose and blur limits were calibrated on one person's 10 real
# photos on 2026-11-03, which turned 0.12 to 0.17 sideways, tilted 0.06 to 0.19 and scored 330 to 595 sharp: provisional
ENROLMENT_MIN_TURN = 0.08          # nose offset over eye distance, left_30 and right_30 against front
ENROLMENT_MIN_TILT = 0.04          # nose height between eyes and mouth, chin_up and chin_down against front
ENROLMENT_MAX_FRONT_TURN = 0.10    # the front photo must face the camera
ENROLMENT_MIN_SHARPNESS = 40       # Laplacian variance of the face at 112 x 112; 3 px of added blur gave 54, 5 px gave 20
ENROLMENT_MAX_PHOTO_BYTES = 2 * 1024 * 1024
ENROLMENT_MIN_SHORT_SIDE = 480     # px

# Maximum number of images saved per cluster per person
NUMBER_OF_PICTURES = 3

# API address for dynamic facial dataset collection service
DYNAMIC_FACE_DATA_COLLECTOR_API = "http://dynamic-face-dataset-collector:8000"  # service name: this client's own collector (D-036)

# PostgreSQL Database Name
POSTGRESQL_DATABASE_NAME = client_name("Face_Recognition_Database")

# Timeout if not getting response from API
TIMEOUT = 5 * 60
########################################################################################################################


########################################################################################################################
# Parameters specific to Database Server Which Connects to Database (REDIS)
########################################################################################################################
# DATABASE Host
DATABASE_HOST = "mfr-database-controller"  # service name: this client's own controller, not published on the host (D-036)

# DATABASE port
DATABASE_PORT = 20001

# Boolean flag to indicate whether to enable the database server
ENABLE_DATABASE_SERVER = True
########################################################################################################################


########################################################################################################################
# Parameters specific to PostgreSQL Database
########################################################################################################################
# PostgreSQL Host
POSTGRESQL_HOST = IP_ADDRESS

# PostgreSQL port on the host; a host whose 5432 is taken publishes another one (POSTGRES_HOST_PORT in .env)
POSTGRESQL_PORT = int(os.getenv("POSTGRESQL_PORT", "5432"))

# PostgreSQL Database Name
POSTGRESQL_DATABASE = client_name("CCTV_Camera_Surveillance")

# If the person is recognized by the same camera within this time threshold, the entry will not be added to the database
SAME_CAM_TIME_ENTRY_THRESHOLD = 5    # minutes
########################################################################################################################


########################################################################################################################
# Parameters specific to Feedback Server Which Connects to Feedback Message Publisher (CONFLUENT-KAFKA)
########################################################################################################################
# FEEDBACK Host
FEEDBACK_HOST = "mfr-feedback-controller"  # service name: this client's own controller, not published on the host (D-036)

# FEEDBACK port
FEEDBACK_PORT = 20012
########################################################################################################################


########################################################################################################################
# Parameters specific to Feedback given to the user
########################################################################################################################
# Wait time for API response in seconds
API_RESPONSE_TIMEOUT = 1 * 60

# Boolean flag to indicate whether to save the recognition frames
SAVE_RECOGNITION_FRAMES = False

# Boolean flag to indicate whether to enable the feedback server
ENABLE_FEEDBACK_SERVER = True

# File path where the recognition frames will be saved
RECOGNITION_PATH = "Recognition_Frames"

# Time after which the status is reset
STATUS_THRESHOLD = 1 * 60  # 1 minutes

# Time for which the kafka messages will be retained
KAFKA_MESSAGE_RETENTION = 5 * 1000  # 5 seconds
SEGMENT_RETENTION_TIME = 5 * 1000  # 5 seconds

# Kafka host
KAFKA_HOST = IP_ADDRESS
# Kafka port
KAFKA_PORT = "9092"
# Topics are <prefix><location>_<point>. A dot ends the prefix: IDs hold none, so one client's prefix never covers another's topics
KAFKA_TOPIC_PREFIX = "" if LEGACY_SHARED_SERVICES else f"{CLIENT_ID}."  # the owner too after its cutover (D-037)


# Sessions and login throttling (D-036 step 4)
SESSION_HOURS = 8
LOGIN_ATTEMPTS = 5  # failed logins for one name within the window before it is refused
LOGIN_WINDOW_MINUTES = 15

# Display face image server port
DISPLAY_FACE_IMAGE_SERVER_PORT = 20013
########################################################################################################################
