# -*- coding: utf-8 -*-
"""
@Author: Anubhav Patrick, Hamza Aziz
"""

# importing the required libraries
import json
import io
import cv2
import socket
import time
import requests
from custom_logging import multicam_server_logger
from face_liveness_detection import face_liveness_detection
from inference_data_cleaner import feedback_data_formatter, data_formatter, collect_cropped_face_data
from milvus_server import search_embedding
from parameters import ENABLE_FEEDBACK_SERVER, \
    ENABLE_DATABASE_SERVER, \
    DATABASE_HOST, \
    DATABASE_PORT, \
    FEEDBACK_HOST, \
    FEEDBACK_PORT, \
    ENABLE_FACE_LIVENESS_DETECTION, \
    DYNAMIC_FACE_DATA_COLLECTOR_API, \
    SAVE_FACE
from custom_logging import database_server_logger, dynamic_face_data_collector_logger
from util.face_data_client import submit_faces_async

# kafka_CONSUMER = create_kafka_CONSUMER()
error_encounter = 0


def load_with_retry(collection, retry_interval=10):
    """
    Keep calling collection.load() until it succeeds,
    retrying on MilvusException code 700 (index not found).
    """
    while True:
        try:
            collection.load()
            # multicam_server_logger.info(f"Collection {collection.name} loaded successfully.")
            break
        except Exception as error:
            multicam_server_logger.error(f"Collection {collection.name} unable to load due to error: {error}. Retrying in {retry_interval} seconds")
            time.sleep(retry_interval)


def batched_frame_face_recognition(
        ifr_client,
        thread_name: str,
        batch_of_frames: list,
        batch_of_cam_names: list,
        batch_of_cam_ips: list,
        embeddings_collection,
        staging_collection
):
    # print(batch_of_frames)
    """
    This function is to be used for GPU based face recognition.
    It performs face detection on a batch of frames at a time.

    Arguments:
        ifr_client: InsightFace-REST database_client to establish connection
        thread_name: Thread name of the current thread in process
        batch_of_frames: List of frames
        batch_of_cam_names: List of camera names
        batch_of_cam_ips: List of camera ip addresses
        embeddings_collection: A collection of embeddings of known faces
        staging_collection: A collection of embeddings of faces captured from CCTV footage
    """
    global error_encounter    # , kafka_CONSUMER
    load_with_retry(staging_collection)

    # USE EXCEPTION HANDLING TO HANDLE ERRORS THAT MAY OCCUR DURING BATCH PROCESSING
    try:
        error_encounter = 0
        ################################################################################################################
        # PERFORM FACE RECOGNITION ON THE BATCH OF FRAMES
        ################################################################################################################
        # Get the face encodings, bounding boxes' coordinates, corresponding frames and cameras with their ip addresses
        # current_face_encoding_start_time = time.perf_counter()
        batch_information = ifr_client.batch_face_locations(batch_of_frames, batch_of_cam_names, batch_of_cam_ips)
        # print(batch_information)

        # initialize to None to prevent any exceptions
        face_encodings_list, bounding_boxes_list, frames_list, cameras_list, ip_addresses_list, face_array_list, landmarks_list = (None, None, None, None, None, None, None)
        # Perform face liveness detection on the batch of frames before the recognition
        if ENABLE_FACE_LIVENESS_DETECTION or SAVE_FACE:
            face_encodings_list, bounding_boxes_list, frames_list, cameras_list, ip_addresses_list, face_array_list, landmarks_list = batch_information
        else:
            face_encodings_list, bounding_boxes_list, frames_list, cameras_list, ip_addresses_list = batch_information

        # multicam_server_logger.debug(f"BATCH INFORMATION: {batch_information}")
        # current_face_encoding_end_time = time.perf_counter()
        # time_taken_to_get_current_face_encoding = current_face_encoding_end_time - current_face_encoding_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to get current real faces encoding is {time_taken_to_get_current_face_encoding:.6f} seconds"
        # )

        # Perform face recognition on the batch of frames by searching the embeddings in Milvus server
        # similarity_search_start_time = time.perf_counter()
        result = search_embedding(embeddings_collection, face_encodings_list)
        # multicam_server_logger.debug(f"Result: {result}")
        cctv_result = search_embedding(staging_collection, face_encodings_list)
        # multicam_server_logger.debug(f"CCTV Result: {cctv_result}")
        # print(result)
        # similarity_search_end_time = time.perf_counter()
        # similarity_search_time = similarity_search_end_time - similarity_search_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken for similarity search is {similarity_search_time:.6f} seconds"
        # )
        ################################################################################################################

        ################################################################################################################
        # AFTER PERFORMING FACE RECOGNITION ON THE BATCH OF FRAMES, SEND THE RESULTS TO THE
        # DATABASE SERVER (REDIS) FOR STORING THE RECOGNITION RESULTS IN THE DATABASE, AND
        # FEEDBACK SERVER (KAFKA) FOR SENDING THE RECOGNITION RESULTS TO THE FEEDBACK SERVER TO BE DISPLAYED TO THE USER
        # Also, save the recognition frames if SAVE_RECOGNITION_FRAMES is True
        ################################################################################################################
        # Format the result of pymilvus search
        # format_result_start_time = time.perf_counter()
        formatted_result = data_formatter(result, cctv_result, cameras_list, ip_addresses_list, frames_list, bounding_boxes_list)
        # multicam_server_logger.debug(f"FINAL RESULT: {formatted_result}")
        # print(formatted_result)
        feedback_result = feedback_data_formatter(result, cameras_list, ip_addresses_list)
        # print(feedback_result)
        # print()
        # print(f"ORIGINAL: {formatted_result.keys()}")
        # print()
        # format_result_end_time = time.perf_counter()
        # format_result_total_time = format_result_end_time - format_result_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to format the raw inference results is {format_result_total_time:.6f} seconds"
        # )

        if ENABLE_FACE_LIVENESS_DETECTION:
            cropped_faces_data = collect_cropped_face_data(result, cameras_list, face_array_list, landmarks_list)
            for person_id, cropped_faces_list in cropped_faces_data.items():
                # print(face_liveness_detection(person_id, cropped_faces_list), f"List Size: {len(cropped_faces_list)}")
                # face_liveness_start_time = time.time()
                person_face_liveness = face_liveness_detection(person_id, cropped_faces_list)
                # face_liveness_end_time = time.time()
                # face_liveness_total_time = face_liveness_end_time - face_liveness_start_time
                # multicam_server_logger.info(
                #     f"Time taken to perform face liveness detection via API on the batch of faces of size {len(cropped_faces_list)} is {round((face_liveness_total_time * 1000), 2)} milliseconds"
                # )
                # print(f"\n{person_face_liveness}, List Size: {len(cropped_faces_list)}\n")
                if "error" in person_face_liveness:
                    multicam_server_logger.error(
                        f"Error while detecting face liveness for {person_id}: {person_face_liveness['error']}"
                    )
                else:
                    liveness_counter = person_face_liveness[person_id]
                    real_count = liveness_counter.get("Real Face", 0)
                    fake_count = liveness_counter.get("Spoof Face", 0)
                    # print(real_count < fake_count)
                    if real_count < fake_count:
                        formatted_result.pop(person_id)
                        # corresponding_value = formatted_result.pop(person_id)
                        # database_server_logger.warn(f"Person {person_id} with details {corresponding_value} is a spoofing attempt.")

        # Get the current date and time; at which, the person id recognized
        current_time = time.strftime("%H:%M:%S")    # current time in 24-hour format as HH:MM:SS
        current_date = time.strftime("%Y-%m-%d")    # current date in YYYY-MM-DD format

        # print()
        # print(f"FILTERED: {formatted_result.keys()}")
        # print()
        # data_encoding_start_time = time.perf_counter()
        # Create a dictionary of the data to be sent to the database server and feedback server
        data_to_send = {
            'current_date': current_date,
            'current_time': current_time,
            'results': formatted_result
        }
        # print(data_to_send)

        feedback_data = {
            'current_date': current_date,
            'current_time': current_time,
            'results': feedback_result
        }
        # print(data_to_send['results'].keys())

        # Encode the data to be sent
        data_to_send_encoded = json.dumps(feedback_data).encode('utf-8')
        # print(feedback_data)
        # data_encoding_end_time = time.perf_counter()
        # data_encoding_total_time = data_encoding_end_time - data_encoding_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to encode the inference results is {data_encoding_total_time:.6f} seconds"
        # )

        # data_sending_start_time = time.perf_counter()
        # Check if the database server is enabled
        if ENABLE_DATABASE_SERVER and formatted_result:
            # Build the URL for the FastAPI ingestion endpoint.
            url = f"http://{DATABASE_HOST}:{DATABASE_PORT}/ingest"
            try:
                # Use the "json" parameter to let requests handle encoding and proper content-type.
                response = requests.post(url, json=data_to_send, timeout=5)

                if response.status_code == 200:
                    pass
                    # database_server_logger.info("Data sent successfully:", response.json())
                else:
                    database_server_logger.error(f"Failed to send data. Status code: {response.status_code}. Response: {response.text}")
            except Exception as e:
                database_server_logger.error("Exception sending data to database server:", e)
        # data_sending_end_time = time.perf_counter()
        # data_sending_total_time = data_sending_end_time - data_sending_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to send inference results to SQL Database Server is {data_sending_total_time:.6f} seconds"
        # )

        # feedback_sending_start_time = time.perf_counter()
        # Check if the feedback server is enabled
        if ENABLE_FEEDBACK_SERVER is True:
            feedback_server_ip = FEEDBACK_HOST  # IP of the machine where the feedback server is running
            feedback_server_port = FEEDBACK_PORT  # Port on which the feedback server is listening
            feedback_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Create a socket object
            feedback_client.connect((feedback_server_ip, feedback_server_port))  # Connect to the feedback server
            feedback_client.send(data_to_send_encoded)    # Send the data to the feedback server
        # feedback_sending_end_time = time.perf_counter()
        # feedback_sending_total_time = feedback_sending_end_time - feedback_sending_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to send inference results to Kafka Server is {feedback_sending_total_time:.6f} seconds"
        # )

        if SAVE_FACE:
            # Gather and clean your batch’s face data
            cropped_faces_data = collect_cropped_face_data(
                inference_result=result,
                camera_list=cameras_list,
                face_array_list=face_array_list,
                landmarks_list=landmarks_list,
            )
            submit_faces_async(cropped_faces_data, DYNAMIC_FACE_DATA_COLLECTOR_API)
        ################################################################################################################

    except Exception as e:
        error_encounter += 1

        if error_encounter >= 10:
            # error_message = "ERROR: Unexpected Error Occurred"

            # for camera in IP_CAMS:
            #     kafka_topic = f"{KAFKA_TOPIC_NAME_PREFIX}_{camera}"
            #     kafka_CONSUMER.produce(kafka_topic, key="ERROR", value=error_message.encode('utf-8'))
            #     kafka_CONSUMER.flush()

            multicam_server_logger.error(
                f'Thread: {thread_name} - Error in batched_face_locations: {e}'
            )

            error_encounter = 0
