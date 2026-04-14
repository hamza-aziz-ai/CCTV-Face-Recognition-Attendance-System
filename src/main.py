import multiprocessing
import signal
import time
import sys

from custom_logging import multicam_server_logger
from feedback_server.feedback_message_kafka_publisher import \
    delete_kafka_topics, \
    create_kafka_topics
from milvus_server import create_connection, create_collection
from multicam_stream_consumer import consumer_main
from multicam_stream_producer import producer_main, cameras
from multiprocessing_shared_buffer import MULTIPROCESS_SHARED_BUFFER
from parameters import MILVUS_COLLECTION_NAME, TOPIC_DELETION_WAIT_TIME, MILVUS_STAGING_COLLECTION_NAME


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


def signal_handler(sig, frame):
    print('Received signal to stop. Cleaning up...')

    if producer_process is not None:
        producer_process.terminate()
        producer_process.join()
        multicam_server_logger.warning('Producer process terminated')

    for cam in cameras:
        cam.release()
        del cam

    delete_kafka_topics()
    multicam_server_logger.warning("Kafka topics deleted")
    try:
        del MULTIPROCESS_SHARED_BUFFER
        multicam_server_logger.warning("Deleting Shared Queue")
    except Exception as error:
        multicam_server_logger.warning(f"Error in Deleting Shared Queue due to error: {error}")
    multicam_server_logger.warning("EXITING THE PROGRAM...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
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
    # ESTABLISH CONNECTION WITH KAFKA SERVER AND CREATE FRESH TOPICS
    ####################################################################################################################
    # Delete the existing Kafka topics
    delete_kafka_topics()

    # Wait for 10 seconds for the Kafka topics to be deleted
    time.sleep(TOPIC_DELETION_WAIT_TIME)

    # Create Kafka topic with the specified number of partitions
    create_kafka_topics()

    # Wait for 60 seconds for the Kafka topics to be created
    time.sleep(TOPIC_DELETION_WAIT_TIME)
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
    try:
        consumer_main(MULTIPROCESS_SHARED_BUFFER, embeddings_collection, staging_collection)
    except Exception as e:
        signal_handler(None, None)

    producer_process.join()
    # consumer_process.join()
