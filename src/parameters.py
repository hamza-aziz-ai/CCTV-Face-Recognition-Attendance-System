"""
This module contains the default parameters used by the app
"""
from dotenv import load_dotenv
import os


########################################################################################################################
# Project Configuration for each INSTITUTE
########################################################################################################################
load_dotenv("master.env")
INSTITUTE = os.getenv("INSTITUTE")
IP_ADDRESS = os.getenv("IP_ADDRESS")

CAMERA_CONFIGURATION_FILE = f"src/Camera-Configuration/{INSTITUTE}/camera_configuration.json"

# Set video frame height and width
FRAME_HEIGHT = 360  # 720 #576
FRAME_WIDTH = 640  # 1280 #1024
# Desirable frame size (or frame area)
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT
########################################################################################################################

########################################################################################################################
# Parameters specific to Project Paths
########################################################################################################################
FACIAL_RECOGNITION_DATASET_PATH = f"FACIAL-RECOGNITION-DATASET/{INSTITUTE}"
DYNAMIC_DATASET_PATH = f"DYNAMIC-FACIAL-RECOGNITION-DATASET/{INSTITUTE}"
FACIAL_RECOGNITION_EMBEDDINGS_PATH = f"{FACIAL_RECOGNITION_DATASET_PATH}/FACE_EMBEDDINGS"
DYNAMIC_DATASET_EMBEDDINGS_PATH = f"{DYNAMIC_DATASET_PATH}/FACE_EMBEDDINGS"
DISPLAY_FACE_IMAGE_PATH = f"DISPLAY-FACE-DATASET/{INSTITUTE}"
FACE_LANDMARKS_PATH = f"FACE-LANDMARKS/{INSTITUTE}"
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

# set BATCH_SIZE for face detection
BATCH_SIZE = 32  # for DGX 64, 8 for CPU

# buffer size for video streaming to minimize inconsistent network conditions
LIVE_STREAM_BUFFER_SIZE = 4096

# buffer size for frames on which face recognition will be performed
LIVE_STREAM_BUFFER_PURGE_SIZE = 256  # 256 for DGX

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
########################################################################################################################


########################################################################################################################
# Parameters specific to InsightFace-REST face detection
########################################################################################################################
# InsightFace-REST host
INSIGHTFACE_HOST = f"http://{IP_ADDRESS}"

# InsightFace-REST port
INSIGHTFACE_PORT = "6385"  # 6385 for DGX, 18081 for the local system

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

# Vector metric type and index type
METRIC_TYPE = "COSINE"
INDEX_TYPE = "GPU_IVF_FLAT"

# Threshold
FACE_MATCHING_TOLERANCE = 0.5 if METRIC_TYPE == "COSINE" else 0.9    # For L2 Metric Type

# Milvus collection name
# MILVUS_COLLECTION_NAME = "TEST_COLLECTION"
MILVUS_COLLECTION_NAME = f"{INSTITUTE}_FACE_DATA_COLLECTION_FOR_{METRIC_TYPE}"
########################################################################################################################


########################################################################################################################
# Parameters specific to dynamic facial dataset collection
########################################################################################################################
# Milvus staging collection name for face recognition fallback
MILVUS_STAGING_COLLECTION_NAME = f"{INSTITUTE}_FACE_DATA_STAGING_COLLECTION_FOR_{METRIC_TYPE}"

# Boolean flag to indicate whether to do staging
STAGING = True

# Boolean flag to indicate to collect facial dataset at runtime
SAVE_FACE = True

# Threshold value for distance between two eye landmarks to decide whether the face is large enough to save
PUPIL_DISTANCE_THRESHOLD = 28    # px

# Maximum number of images saved per cluster per person
NUMBER_OF_PICTURES = 3

# API address for dynamic facial dataset collection service
DYNAMIC_FACE_DATA_COLLECTOR_API = f"http://{IP_ADDRESS}:8000"

# PostgreSQL Database Name
POSTGRESQL_DATABASE_NAME = f"{INSTITUTE}_Face_Recognition_Database"

# Timeout if not getting response from API
TIMEOUT = 5 * 60
########################################################################################################################


########################################################################################################################
# Parameters specific to Database Server Which Connects to Database (REDIS)
########################################################################################################################
# DATABASE Host
DATABASE_HOST = IP_ADDRESS  # IP of the machine where the database is running

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

# PostgreSQL port
POSTGRESQL_PORT = 5432

# PostgreSQL Database Name
POSTGRESQL_DATABASE = f"{INSTITUTE}_CCTV_Camera_Surveillance"

# If the person is recognized by the same camera within this time threshold, the entry will not be added to the database
SAME_CAM_TIME_ENTRY_THRESHOLD = 5    # minutes
########################################################################################################################


########################################################################################################################
# Parameters specific to Feedback Server Which Connects to Feedback Message Publisher (CONFLUENT-KAFKA)
########################################################################################################################
# FEEDBACK Host
FEEDBACK_HOST = IP_ADDRESS  # IP of the machine where the database is running

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

# Wait time for Kafka topics to be deleted
TOPIC_DELETION_WAIT_TIME = 30

# Display face image server port
DISPLAY_FACE_IMAGE_SERVER_PORT = 20013
########################################################################################################################
