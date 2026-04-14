"""
This module is created to save the frames on which face recognition is performed.

Date created: 28th July 2023
Author: Hamza Aziz
"""

import os
from datetime import datetime

import cv2
import numpy

from custom_logging import feedback_server_logger
from parameters import RECOGNITION_PATH, SAME_CAM_TIME_ENTRY_THRESHOLD


def create_date_directory(current_date: str):
    """
    This function will create a directory with the name of the current date.

    Parameters:
        current_date: This is the date at which the person is recognized.
    """
    directory_path = os.path.join(RECOGNITION_PATH, current_date)
    try:
        os.makedirs(directory_path, exist_ok=True)
        # feedback_server_logger.info(f"Directory '{directory_path}' created or already exists.")
        return True
    except FileExistsError:
        feedback_server_logger.exception(f"Directory '{directory_path}' already exists and cannot be created.")


def create_person_directory(person_id: str, current_date: str, is_recognized: bool):
    """
    This function will create a directory with the name of the person.

    Parameters:
        person_id: This is the ID of the person recognized.
        current_date: This is the date at which the person is recognized.
        is_recognized: This is a flag to mark whether the face vector matching distance is under a specified threshold.
    """
    IS_RECOGNIZED = "RECOGNIZED-PEOPLE" if is_recognized else "UNRECOGNIZED-PEOPLE"
    directory_path = os.path.join(RECOGNITION_PATH, current_date, IS_RECOGNIZED, person_id)
    try:
        os.makedirs(directory_path, exist_ok=True)
        # feedback_server_logger.info(f"Directory '{directory_path}' created or already exists.")
        return True
    except FileExistsError:
        feedback_server_logger.exception(f"Directory '{directory_path}' already exists and cannot be created.")


def create_camera_directory(camera_name: str, current_date: str, person_id: str, is_recognized: bool):
    """
    This function will create a directory with the name of the camera.

    Parameters:
        camera_name: This is the ID of the camera under which the person is recognized.
        current_date: This is the date at which the person is recognized.
        person_id: This is the ID of the person recognized.
        is_recognized: This is a flag to mark whether the face vector matching distance is under a specified threshold.
    """
    IS_RECOGNIZED = "RECOGNIZED-PEOPLE" if is_recognized else "UNRECOGNIZED-PEOPLE"
    directory_path = os.path.join(RECOGNITION_PATH, current_date, IS_RECOGNIZED, person_id, camera_name)
    try:
        os.makedirs(directory_path, exist_ok=True)
        # feedback_server_logger.info(f"Directory '{directory_path}' created or already exists.")
        return True
    except FileExistsError:
        feedback_server_logger.exception(f"Directory '{directory_path}' already exists and cannot be created.")


def save_frame(
        frame: numpy.ndarray,
        bbox: list,
        recognition_date: str,
        person_id: str,
        camera_name: str,
        camera_ip: str,
        recognition_time: str,
        percentage_similarity: float,
        is_recognized: bool
) -> bool:
    """
    This function will save the frames on which face recognition is performed.

    Parameters:
        frame: This is the frame on which the person is recognized.
        bbox: This is the bounding box's coordinates of the person recognized.
        recognition_date: This is the date at which the person is recognized.
        person_id: This is the ID of the person recognized.
        camera_name: This is the name or location of the camera under which the person is recognized.
        camera_ip: This is the IP address of the camera under which the person is recognized.
        recognition_time: This is the time at which the person is recognized.
        percentage_similarity: This is the distance of the recognized face from the camera.
        is_recognized: This is a flag to indicate that the person recognized is within a certain threshold value (confidence)

    Returns:
        True if the frame is saved successfully, else False.
    """
    try:
        IS_RECOGNIZED = "RECOGNIZED-PEOPLE" if is_recognized else "UNRECOGNIZED-PEOPLE"

        file_path = os.path.join(
            RECOGNITION_PATH, recognition_date, IS_RECOGNIZED, person_id, camera_name,
            f"feedback_image__{person_id}__{recognition_time}.jpg"
        )

        if is_recognized:
            # Draw the bounding box
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            text = f"Date: {recognition_date}\nID: {person_id}\nCamera Name: {camera_name}\nCamera IP: {camera_ip}\nTime: {recognition_time}\nSimilarity Percentage: {percentage_similarity}%"

        else:
            # Draw the bounding box
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)
            text = f"Date: {recognition_date}\nPOSSIBLE ID: {person_id}\nCamera Name: {camera_name}\nCamera IP: {camera_ip}\nTime: {recognition_time}\nSimilarity Percentage: {percentage_similarity}%"

        # # Resize the frame
        # frame = cv2.resize(frame, (1920, 1080))

        # Define the text and its parameters
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        font_color = (255, 255, 255)  # White color
        font_thickness = 1
        line_height = 20  # Vertical spacing between lines
        text_margin = 10  # Margin from the top and left edges

        # Split the text into lines
        text_lines = text.split('\n')

        # Calculate the maximum text width and total text height
        max_line_width = max(cv2.getTextSize(line, font, font_scale, font_thickness) for line in text_lines)[0][0]
        text_width = max_line_width + 2 * text_margin
        text_height = len(text_lines) * line_height + 2 * text_margin

        # Create a black rectangle in the top left corner
        cv2.rectangle(frame, (0, 0), (text_width, text_height), (0, 0, 0), thickness=cv2.FILLED)

        # Put the text on the image (left-aligned within the rectangle)
        y = text_margin + line_height  # Start below the top margin
        for line in text_lines:
            cv2.putText(
                frame, line, (text_margin, y), font, font_scale, font_color, font_thickness, lineType=cv2.LINE_AA
            )
            y += line_height

        # Save the frame
        cv2.imwrite(file_path, frame)
        # feedback_server_logger.info(f"Feedback frame saved at {file_path}")
        return True

    except Exception as e:
        feedback_server_logger.exception(f"Exception occurred while saving feedback frame: {e}")
        return False


def save_single_feedback_frame(
        person_id: str,
        is_recognized: bool,
        camera_name: str,
        camera_ip: str,
        percentage_similarity: float,
        frame: numpy.ndarray,
        bbox: list,
        current_date: str = datetime.now().strftime("%d-%m-%Y"),
        current_time: str = datetime.now().strftime("%H:%M:%S")
):
    """
    This function will save the frames on which face recognition is performed.

    Parameters:
        person_id: This is the ID of the person recognized.
        is_recognized: This is a flag to indicate that the person recognized is within a certain threshold value (confidence)
        camera_name: This is the name or location of the camera under which the person is recognized.
        camera_ip: This is the IP address of the camera under which the person is recognized.
        percentage_similarity: This is the distance of the recognized face from the camera.
        frame: This is the frame on which the person is recognized.
        bbox: This is the bounding box's coordinates of the person recognized.
        current_date: The current date in the format DD-MM-YYYY.
        current_time: The current time in the format HH_MM_SS.
    """

    IS_RECOGNIZED = "RECOGNIZED-PEOPLE" if is_recognized else "UNRECOGNIZED-PEOPLE"

    try:
        # Check if the current date directory exists
        # If the current date directory does not exist, create a new directory for the current date
        if not os.path.exists(os.path.join(RECOGNITION_PATH, current_date)):
            # Create a directory with the name of the current date
            if create_date_directory(current_date):
                # Create a directory with the ID of the person
                if create_person_directory(person_id, current_date, is_recognized):
                    # Create a directory with the name of the camera
                    if create_camera_directory(camera_name, current_date, person_id, is_recognized):
                        # Save the frame
                        save_frame(
                            frame, bbox, current_date, person_id, camera_name, camera_ip, current_time, percentage_similarity, is_recognized
                        )
        else:
            # Check if the current person directory exists
            # If the current person directory does not exist,
            # create a new directory for the current person
            if not os.path.exists(os.path.join(RECOGNITION_PATH, current_date, IS_RECOGNIZED, person_id)):
                # Create a directory with the ID of the person
                if create_person_directory(person_id, current_date, is_recognized):
                    # Create a directory with the name of the camera
                    if create_camera_directory(camera_name, current_date, person_id, is_recognized):
                        # Save the frame
                        save_frame(
                            frame, bbox, current_date, person_id, camera_name, camera_ip, current_time, percentage_similarity, is_recognized
                        )
            else:
                # Check if the current camera directory exists
                # If the current camera directory does not exist,
                # create a new directory for the current camera
                if not os.path.exists(os.path.join(RECOGNITION_PATH, current_date, IS_RECOGNIZED, person_id, camera_name)):
                    # Create a directory with the name of the camera
                    if create_camera_directory(camera_name, current_date, person_id, is_recognized):
                        # Save the frame
                        save_frame(
                            frame, bbox, current_date, person_id, camera_name, camera_ip, current_time, percentage_similarity, is_recognized
                        )
                else:
                    # Get the time at which the last frame was saved
                    try:
                        # List all files in the specified directory
                        files = os.listdir(
                            os.path.join(RECOGNITION_PATH, current_date, IS_RECOGNIZED, person_id, camera_name)
                        )

                        # Extract and sort files based on the recognition time
                        files_sorted = sorted(files, key=lambda x: datetime.strptime(x.split("__")[-1].split(".")[0],
                                                                                     "%H:%M:%S"))

                        # Get the latest file
                        last_frame_saved = files_sorted[-1]
                        last_frame_time = last_frame_saved.split("__")[-1].split(".")[0]
                        # Check if the time difference between the current time and the last frame time is greater
                        # than SAME_CAM_TIME_ENTRY_THRESHOLD minutes
                        time_difference = datetime.strptime(current_time, "%H:%M:%S") - datetime.strptime(last_frame_time, "%H:%M:%S")
                        if time_difference.seconds >= SAME_CAM_TIME_ENTRY_THRESHOLD:
                            # Save the frame
                            save_frame(
                                frame,
                                bbox,
                                current_date,
                                person_id,
                                camera_name,
                                camera_ip,
                                current_time,
                                percentage_similarity,
                                is_recognized
                            )
                    except IndexError as error:
                        feedback_server_logger.error(f"Error occurred while getting the last frame time: {error}")

    except Exception as e:
        feedback_server_logger.exception(f"Exception occurred while saving feedback frame: {e}")


def save_batched_feedback_frames(recognition_date: str, recognition_time: str, formatted_result) -> bool:
    """
    This function receives the inference result of a batch and saves it to the feedback.

    Parameters:
        recognition_date: This is the date at which the person is recognized.
        recognition_time: This is the time at which the person is recognized.
        formatted_result: This is the formatted result of the inference.

    Returns:
        True if the feedback frames are saved successfully, else False.
    """
    # Iterate over the ID wise results
    for person_id, person_result in formatted_result.items():
        # Iterate over the camera wise results
        for camera_name, camera_ip, percentage_similarity, frame, bbox, is_recognized in person_result:
            try:
                save_single_feedback_frame(
                    person_id,
                    is_recognized,
                    camera_name,
                    camera_ip,
                    percentage_similarity,
                    frame,
                    bbox,
                    recognition_date,
                    recognition_time
                )
            except Exception as e:
                feedback_server_logger.exception(f"Exception occurred while saving feedback frame: {e}")
                return False
    return True
