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
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka import Producer

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)
from custom_logging import feedback_server_logger
from parameters import KAFKA_HOST, \
    KAFKA_PORT, \
    KAFKA_MESSAGE_RETENTION, \
    SEGMENT_RETENTION_TIME, \
    CAMERA_CONFIGURATION_FILE, \
    TOPIC_DELETION_WAIT_TIME
from util.generic_utilities import count_cameras, map_camera_to_kafka_topic_and_partition


# Define Kafka producer configuration
producer_config = {
    "bootstrap.servers": f"{KAFKA_HOST}:{KAFKA_PORT}",  # Replace with your Kafka broker(s) address
    "client.id": "feedback_message_publisher"
}

# Create an AdminClient instance
admin_client = AdminClient(producer_config)

# Define the Kafka topic configuration
kafka_topic_config = {
    "retention.ms": KAFKA_MESSAGE_RETENTION,      # Set the retention time to 10 seconds
    "segment.ms": SEGMENT_RETENTION_TIME          # This will ensure segments are created frequently enough to allow timely purging.
}

topics_list = list()
topics_to_delete = list()
kafka_topics = count_cameras()
camera_to_topic_and_partition = map_camera_to_kafka_topic_and_partition()

for topic_name, number_of_partitions in kafka_topics.items():
    if number_of_partitions == 0:
        continue
    kafka_topic = NewTopic(topic=topic_name, num_partitions=number_of_partitions, replication_factor=1, config=kafka_topic_config)
    topics_list.append(kafka_topic)
    topics_to_delete.append(topic_name)


def create_kafka_topics():
    """
    This function creates a Kafka topic with the specified number of partitions.
    """
    global admin_client, topics_list

    try:
        admin_client.create_topics(topics_list)
        # print(f"Created Kafka topics: '{kafka_topics}'")
        feedback_server_logger.info(f"Created Kafka topics: '{topics_list}'")
    except Exception as e:
        # print(f"Error in creating Kafka Topics due to {e}")
        feedback_server_logger.error(f"Error in creating Kafka Topics due to '{e}'")


def delete_kafka_topics():
    """
    This function deletes the Kafka topic.
    """
    global admin_client, topics_to_delete

    try:
        admin_client.delete_topics(topics_to_delete)
        # print(f"Deleted Kafka topic {topics_to_delete}")
        feedback_server_logger.warning(f'Topics: "{topics_to_delete}" scheduled for deletion.')
        feedback_server_logger.info(f"Waiting {TOPIC_DELETION_WAIT_TIME} seconds for the topics to be deleted.")
    except Exception as e:
        # print(f"Error in deleting Kafka Topics due to {e}")
        feedback_server_logger.error(f"Error in deleting Kafka Topics due to '{e}'")


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
