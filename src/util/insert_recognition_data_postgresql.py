import os
import psycopg2
import time
import numpy
import cv2
from datetime import datetime, timedelta
from typing import Optional
from numpy import ndarray

# Database connection setup
DB_CONFIG = {
    'dbname': 'facial_recognition_results',
    'user': 'postgres',
    'password': os.environ.get("POSTGRES_PASSWORD"),
    'host': 'localhost',
    'port': os.environ.get("POSTGRESQL_PORT", "5432")
}


FACE_MATCHING_TOLERANCE = 0.9
connection = psycopg2.connect(**DB_CONFIG)
cursor = connection.cursor()


def plot_bbox(
        frame: numpy.ndarray,
        bbox: list,
        person_id: str,
        percentage_similarity: float,
) -> Optional[bytes]:
    """
    This function will plot bounding box on the frames in which the person is recognized.

    Parameters:
        frame: This is the frame on which the person is recognized.
        bbox: This is the bounding box's coordinates of the person recognized.
        person_id: This is the ID of the person recognized.
        percentage_similarity: This is the percentage similarity of the recognized face.

    Returns:
        Encoded frame as binary (bytes) for saving to the database.
    """
    try:
        # Draw the bounding box
        x_min, y_min, x_max, y_max = bbox
        color = (0, 255, 0)
        cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 2)
        cv2.putText(
            frame,
            f"{person_id} ({round(percentage_similarity, 2)}%)",
            (x_min, y_min - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            2,
        )

        # Encode the frame as a JPEG image to save space
        _, encoded_frame = cv2.imencode('.jpg', frame)
        return encoded_frame.tobytes()

    except Exception as e:
        print(f"Exception occurred while plotting bounding box for {person_id} on the frame: {e}")
        return None


def insert_recognition_data(data_to_send):
    """
    Inserts recognition data into the PostgreSQL database, ensuring no duplicate entries
    and respecting the 5-minute rule for re-entries per person per camera.

    Arguments:
        data_to_send (dict): A dictionary containing the current date, current time, and formatted results.
    """
    global connection, cursor
    try:
        # Connect to PostgreSQL database
        connection = psycopg2.connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Prepare data
        current_date = data_to_send['current_date']
        current_time = data_to_send['current_time']
        results = data_to_send['results']

        # Convert the current date and time to PostgreSQL-compatible formats
        formatted_date = time.strftime("%Y-%m-%d", time.strptime(current_date, "%d-%m-%Y"))
        formatted_time = time.strftime("%H:%M:%S", time.strptime(current_time, "%I:%M:%S %p"))

        # Iterate through the formatted results
        for person_id, records in results.items():
            for record in records:
                camera_name, camera_ip, confidence_score, frame, bounding_box = record
                frame = plot_bbox(frame, bounding_box, person_id, confidence_score)

                # Calculate the time threshold (5 minutes earlier)
                current_datetime = datetime.strptime(f"{formatted_date} {formatted_time}", "%Y-%m-%d %H:%M:%S")
                threshold_datetime = current_datetime - timedelta(minutes=5)
                time_threshold = threshold_datetime.strftime("%H:%M:%S")

                print(f"DEBUG: Current time = {formatted_time}, Threshold time = {time_threshold}")

                # Check if an entry exists within the last 5 minutes
                query = """
                SELECT 1 FROM recognition_results
                WHERE person_id = %s
                  AND camera_name = %s
                  AND recognition_date = %s
                  AND recognition_time >= %s;
                """
                cursor.execute(query, (person_id, camera_name, formatted_date, time_threshold))

                # Skip insertion if a recent entry exists
                if cursor.fetchone():
                    print(f"Skipping entry for person_id={person_id} at camera_name={camera_name} (already recorded within 5 minutes).")
                    continue

                # Insert the record into the database
                insert_query = """
                INSERT INTO recognition_results (person_id, camera_name, camera_ip, recognition_date, recognition_time, confidence_score, frame)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """
                cursor.execute(
                    insert_query,
                    (person_id, camera_name, camera_ip, formatted_date, formatted_time, confidence_score, frame)
                )
                print(f"Inserted entry for person_id={person_id} at camera_name={camera_name}.")

        # Commit the transaction
        connection.commit()
        print("Data inserted successfully.")

    except Exception as error:
        print(f"Error while inserting data: {error}")
    finally:
        # Close the database connection
        if connection:
            cursor.close()
            connection.close()

def calculate_euclidean_percentage_similarity(euclidean_distance):
    if euclidean_distance <= FACE_MATCHING_TOLERANCE:
        # For distances between 0 and 0.9, similarity is 100%
        return 100
    else:
        # For distances > 0.9, calculate decreasing similarity
        # Adjusting the range to start decreasing from 0.9 up to 2
        max_distance = 2
        # Scaling the distance beyond 0.9 to fit within the (0 to 1) range
        adjusted_distance = (euclidean_distance - FACE_MATCHING_TOLERANCE) / (max_distance - FACE_MATCHING_TOLERANCE)
        percentage_similarity = (1 - adjusted_distance) * 100
        return max(0, percentage_similarity)  # Ensuring it doesn't go negative



def data_formatter(inference_result, camera_list: list, ip_list: list, frame_list: list, bbox_list: list):
    """
    This function formats the raw inference data of a single batch and cleans it for further use.

    Arguments:
        inference_result: Raw inference result of single batch
        camera_list: List of cameras corresponding to the inference results
        ip_list: List of ip addresses corresponding to the inference results
        frame_list: List of frames corresponding to the inference results
        bbox_list: List of bounding boxes' coordinates corresponding to the inference results

    Returns:
        single_batch_result: Processed inference result of single batch in a dictionary format
    """

    single_batch_result = dict()

    for i, hit in enumerate(inference_result):
        person_id = hit[0]['id']
        cam_name = camera_list[i]
        cam_ip = ip_list[i]
        frame = frame_list[i]
        bbox = bbox_list[i]

        euclidean_distance = hit[0]['distance']
        percentage_similarity = calculate_euclidean_percentage_similarity(euclidean_distance)
        if percentage_similarity >= 60:
            if person_id not in single_batch_result:
                single_batch_result[person_id] = [(cam_name, cam_ip, percentage_similarity, frame, bbox)]
            else:
                single_batch_result[person_id].append((cam_name, cam_ip, percentage_similarity, frame, bbox))

    return single_batch_result


# Example: Using the function
if __name__ == "__main__":
    # Generate current date and time
    current_date = time.strftime("%d-%m-%Y")
    current_time = time.strftime("%I:%M:%S %p")

    # Example inference data
    inference_result = [
        [{'id': '12345', 'distance': 0.4}],
        [{'id': '12345', 'distance': 0.35}]
    ]
    camera_list = ['Entrance Camera', 'Library Camera']
    ip_list = ['192.0.2.1', '192.0.2.2']
    frame_list = [numpy.zeros((480, 640, 3), dtype=numpy.uint8), numpy.zeros((480, 640, 3), dtype=numpy.uint8)]
    bbox_list = [[50, 50, 200, 200], [50, 50, 200, 200]]

    # Format the data
    formatted_result = data_formatter(inference_result, camera_list, ip_list, frame_list, bbox_list)

    # Prepare data to send
    data_to_send = {
        'current_date': current_date,
        'current_time': current_time,
        'results': formatted_result
    }

    # for i in range(2):
        # Insert data into the database
    insert_recognition_data(data_to_send)
