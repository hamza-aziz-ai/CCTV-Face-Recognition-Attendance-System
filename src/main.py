import json
import multiprocessing
import signal
import time
import sys

from custom_logging import multicam_server_logger
from feedback_server.feedback_message_kafka_publisher import ensure_kafka_topics
from milvus_server import create_connection, create_collection
import multicam_stream_consumer
import multicam_stream_producer
from insightface_face_recognition import attendance_sender
from multicam_stream_consumer import consumer_main
from multicam_stream_producer import producer_main, cameras, configured_cameras
from multiprocessing_shared_buffer import MULTIPROCESS_SHARED_BUFFER
from parameters import MILVUS_COLLECTION_NAME, MILVUS_STAGING_COLLECTION_NAME, CAMERA_CONFIGURATION_FILE, NUMBER_OF_THREADS,     THREAD_FLAG, PIPELINE_HEALTH_PORT, INSIGHTFACE_HOST, INSIGHTFACE_PORT, DATABASE_HOST, DATABASE_PORT, FEEDBACK_HOST,     FEEDBACK_PORT, ENABLE_DATABASE_SERVER
from util.pipeline_health import CHECK_DEADLINE, Checks, Workers, readiness, serve


producer_process = None


def load_with_retry(collection, retry_interval=10):
    """
    Keep calling collection.load() until it succeeds,
    retrying on MilvusException code 700 (index not found).
    """
    while True:
        try:
            collection.load()
            multicam_server_logger.info(f"Collection {collection.name} loaded successfully.")
            break
        except Exception as error:
            multicam_server_logger.error(f"Collection {collection.name} unable to load due to error: {error}. Retrying in {retry_interval} seconds")
            time.sleep(retry_interval)


def dependency_checks():
    """What recognition depends on, each check raising when it fails: InsightFace's own self-test runs a real recognition."""
    import socket
    import requests
    from pymilvus import utility
    from feedback_server.feedback_message_kafka_publisher import admin_client

    def get(url):
        requests.get(url, timeout=CHECK_DEADLINE).raise_for_status()

    checks = {
        "insightface": lambda: get(f"{INSIGHTFACE_HOST}:{INSIGHTFACE_PORT}/health"),
        "milvus": lambda: utility.list_collections(timeout=CHECK_DEADLINE),  # this client's database, with its login
        "kafka": lambda: admin_client.list_topics(timeout=CHECK_DEADLINE),
        "feedback": lambda: socket.create_connection((FEEDBACK_HOST, FEEDBACK_PORT), CHECK_DEADLINE).close(),
    }
    if ENABLE_DATABASE_SERVER:
        checks["database"] = lambda: get(f"http://{DATABASE_HOST}:{DATABASE_PORT}/health")
    return checks


def signal_handler(sig, frame):
    print('Received signal to stop. Cleaning up...')

    if producer_process is not None:
        producer_process.terminate()
        producer_process.join()
        multicam_server_logger.warning('Producer process terminated')

    for cam in cameras:
        cam.release()
        del cam

    from insightface_face_recognition import stop_attendance_sender
    stop_attendance_sender()  # sends what is still waiting, and logs what it could not

    multicam_server_logger.warning("EXITING THE PROGRAM...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    started_at = time.monotonic()
    # Progress slots for every camera thread and recognition thread, created before the producer process forks so both
    # processes share them (util/pipeline_health.py)
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_names = [name for name, _ in configured_cameras(json.load(camera_configuration_file))]
    workers = Workers(camera_names, [f"thread_{i}" for i in range(NUMBER_OF_THREADS)] if THREAD_FLAG else [])
    multicam_stream_producer.workers = multicam_stream_consumer.workers = workers
    # milvus_server_start_time = time.time()
    ####################################################################################################################
    # ESTABLISH CONNECTION WITH MILVUS SERVER
    ####################################################################################################################
    # Establishing connection and c
    create_connection()
    embeddings_collection = create_collection(MILVUS_COLLECTION_NAME)
    staging_collection = create_collection(MILVUS_STAGING_COLLECTION_NAME)

    # load the known faces and embeddings
    load_with_retry(embeddings_collection)
    load_with_retry(staging_collection)
    ####################################################################################################################
    # milvus_server_end_time = time.time()
    # milvus_server_total_time = milvus_server_end_time - milvus_server_start_time
    # multicam_server_logger.info(
    #     f"Time taken to establish connection with milvus server is {milvus_server_total_time:>20.9f} seconds"
    # )

    # kafka_server_start_time = time.time()
    ####################################################################################################################
    # ESTABLISH CONNECTION WITH KAFKA SERVER AND MAKE SURE THE TOPICS EXIST
    ####################################################################################################################
    # Create missing topics and add partitions for new cameras; existing topics and their messages stay
    ensure_kafka_topics()
    ####################################################################################################################
    # kafka_server_end_time = time.time()
    # kafka_server_total_time = kafka_server_end_time - kafka_server_start_time
    # multicam_server_logger.info(
    #     f"Time taken to establish connection with milvus server is {kafka_server_total_time:>20.9f} seconds"
    # )

    producer_process = multiprocessing.Process(target=producer_main, args=(MULTIPROCESS_SHARED_BUFFER,))
    # consumer_process = multiprocessing.Process(target=consumer_main, args=(MULTIPROCESS_SHARED_BUFFER,))

    producer_process.start()
    # consumer_process.start()

    # consumer_main(MULTIPROCESS_SHARED_BUFFER, embeddings_collection)
    recognizers = None
    try:
        recognizers = consumer_main(MULTIPROCESS_SHARED_BUFFER, embeddings_collection, staging_collection)
    except Exception as e:
        signal_handler(None, None)

    # The health check starts after the fork, so the producer process never inherits its threads
    sender = attendance_sender()
    checks = Checks(dependency_checks()).start()
    serve(PIPELINE_HEALTH_PORT, lambda: readiness(workers, checks, sender.state, started_at, time.monotonic()))

    if recognizers is None:  # ponytail: only thread mode (the default) hands its workers back to be watched
        producer_process.join()
        sys.exit(1)
    # A worker that dies stops the container, so Docker starts it again: before this, a dead producer or recognition
    # thread left the container running and recognising nobody
    while producer_process.is_alive() and all(thread.is_alive() for thread in recognizers):
        time.sleep(5)
    dead = ["producer process"] if not producer_process.is_alive() else [t.name for t in recognizers if not t.is_alive()]
    multicam_server_logger.error(f"{dead} died; stopping so Docker restarts producer-consumer")
    sender.stop(wait_seconds=10)
    if producer_process.is_alive():
        producer_process.terminate()
        producer_process.join(10)
    sys.exit(1)
    # consumer_process.join()
