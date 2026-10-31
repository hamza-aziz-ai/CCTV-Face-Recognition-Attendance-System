"""
This module is created to publish face recognition feedback messages (to be given to the user) to a Kafka Stream

Reference: https://github.com/confluentinc/confluent-kafka-python
https://docs.confluent.io/kafka-clients/python/current/overview.html#:~:text=Python%20Client%20installation,-The%20client%20is&text=The%20confluent%2Dkafka%20Python%20package,GSSAPI%2C%20see%20the%20installation%20instructions.

Author: Hamza Aziz
Date: 1 September 2023
"""

import os
import sys
import time
import json
from collections import defaultdict
from datetime import datetime
from confluent_kafka.admin import AdminClient, NewPartitions, NewTopic
from confluent_kafka import Producer

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)
from custom_logging import feedback_server_logger
from parameters import LEGACY_SHARED_SERVICES, kafka_login, KAFKA_HOST, \
    KAFKA_PORT, \
    KAFKA_MESSAGE_RETENTION, \
    SEGMENT_RETENTION_TIME, \
    CAMERA_CONFIGURATION_FILE
from util.generic_utilities import count_cameras, map_camera_to_kafka_topic_and_partition


# Define Kafka producer configuration
producer_config = {
    "bootstrap.servers": f"{KAFKA_HOST}:{KAFKA_PORT}",  # Replace with your Kafka broker(s) address
    "client.id": "feedback_message_publisher",
    **kafka_login(),  # this client's SCRAM login (D-037); none for the legacy owner
}

# Create an AdminClient instance
admin_client = AdminClient(producer_config)

# Define the Kafka topic configuration
kafka_topic_config = {
    "retention.ms": KAFKA_MESSAGE_RETENTION,      # Set the retention time to 10 seconds
    "segment.ms": SEGMENT_RETENTION_TIME          # This will ensure segments are created frequently enough to allow timely purging.
}

topics_list = list()
kafka_topics = count_cameras()
camera_to_topic_and_partition = map_camera_to_kafka_topic_and_partition()

for topic_name, number_of_partitions in kafka_topics.items():
    if number_of_partitions == 0:
        continue
    kafka_topic = NewTopic(topic=topic_name, num_partitions=number_of_partitions, replication_factor=1, config=kafka_topic_config)
    topics_list.append(kafka_topic)


def ensure_kafka_topics():
    """
    Creates the topics that are missing and adds partitions when cameras were added. Topics are never deleted, so a
    restart loses no feedback messages and the display can keep reading. Kafka cannot remove partitions, so a topic
    keeps any extra ones after cameras are removed; they stay unused.
    """
    existing = {name: len(meta.partitions) for name, meta in admin_client.list_topics(timeout=10).topics.items()}
    missing = [t for t in topics_list if t.topic not in existing]
    grow = [NewPartitions(t.topic, t.num_partitions) for t in topics_list
            if t.topic in existing and existing[t.topic] < t.num_partitions]
    if not LEGACY_SHARED_SERVICES and (missing or grow):
        # The client may only write to its topics; deploy/provision.py makes them from the camera configuration (D-037)
        raise RuntimeError(f"Kafka topics missing or short of partitions: {[t.topic for t in missing]}, "
                           f"{[p.topic for p in grow]}; rerun deploy/provision.py after changing cameras")
    for futures in ([admin_client.create_topics(missing)] if missing else []) + ([admin_client.create_partitions(grow)] if grow else []):
        for name, future in futures.items():
            future.result()  # raise on failure: producing to a missing topic would lose every message
    feedback_server_logger.info(f"Kafka topics ready: created {[t.topic for t in missing]}, "
                                f"added partitions to {[p.topic for p in grow]}")


def create_kafka_producer(retries=3, delay=5):
    global producer_config
    for attempt in range(retries):
        try:
            producer = Producer(producer_config)
            # feedback_server_logger.info("Successfully created kafka producer")
            return producer
        except Exception as e:
            feedback_server_logger.error(f"Attempt {attempt + 1}/{retries}: Error in creating kafka producer: {e}")
            time.sleep(delay)
    raise Exception("Failed to create kafka producer after multiple attempts")


def feedback_message_publisher(
        producer: Producer,
        formatted_result: dict
):
    """
    This function formats the raw inference data of a single batch, cleans it for further use, and publishes it to
    Kafka.

    Parameters:
        producer: Kafka producer instance
        formatted_result: Formatted result of the inference data
    """
    global camera_to_topic_and_partition
    # print(formatted_result)
    # Publish each item in the single_batch_result to the Kafka topic
    # feedback_server_logger.info()
    for person_id, person_result in formatted_result.items():
        # kafka_message = f"ID: {person_id}"
        # print(kafka_message)
        kafka_message = person_id

        for camera_name, camera_ip, face_distance, is_recognized in person_result:
            # Get the topic based on camera
            kafka_topic_name, topic_partition = camera_to_topic_and_partition[camera_name]

            try:
                if is_recognized:
                    # Publish the message to Kafka
                    producer.produce(topic=kafka_topic_name, partition=topic_partition, key=camera_name, value=kafka_message)
                    # Flush the producer to ensure the message is sent
                    producer.flush()
                    timestamp = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
                    feedback_server_logger.debug(
                        f"[FEEDBACK] Time at which the recognition message `{kafka_message}` is published to Kafka Topic `{kafka_topic_name}:{topic_partition}` is {timestamp}"
                    )
                    # feedback_server_logger.info(f"Successfully published kafka message")
            except Exception as e:
                feedback_server_logger.error(f"Error in publishing message to Kafka for topic {kafka_topic_name} due to exception {e}")

# def feedback_message_publisher(
#         producer: Producer,
#         formatted_result: dict
# ):
#     """
#     This function groups recognized IDs per camera from a single batch and publishes a unique set per camera
#     to the corresponding Kafka partition.
#
#     Parameters:
#         producer: Kafka producer instance
#         formatted_result: Dictionary mapping person_id to a list of tuples:
#                           (camera_name, camera_ip, face_distance, is_recognized)
#     """
#     global camera_to_topic_and_partition
#
#     # Dictionary to hold unique recognized IDs per camera
#     camera_to_ids = defaultdict(set)
#
#     # Aggregate recognized IDs per camera
#     for person_id, person_results in formatted_result.items():
#         for camera_name, _, _, is_recognized in person_results:
#             if is_recognized:
#                 camera_to_ids[camera_name].add(person_id)
#
#     # Publish one batched message per camera
#     for camera_name, recognized_ids in camera_to_ids.items():
#         if not recognized_ids:
#             continue
#
#         kafka_topic_name, topic_partition = camera_to_topic_and_partition[camera_name]
#         kafka_message = json.dumps(list(recognized_ids))  # Send as a simple JSON array
#
#         try:
#             producer.produce(
#                 topic=kafka_topic_name,
#                 partition=topic_partition,
#                 key=camera_name,
#                 value=kafka_message
#             )
#             producer.flush()
#             # Optional logging
#             # timestamp = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
#             # feedback_server_logger.debug(
#             #     f"[FEEDBACK] Published batch message to `{kafka_topic_name}:{topic_partition}` at {timestamp}: {kafka_message}"
#             # )
#         except Exception as e:
#             feedback_server_logger.error(
#                 f"Error in publishing message to Kafka for topic {kafka_topic_name} due to exception {e}"
#             )
