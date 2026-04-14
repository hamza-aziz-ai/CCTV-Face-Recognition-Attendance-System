"""This module writes the data to a file"""

import os
import cv2
import sys
import json
import numpy as np

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import CAMERA_CONFIGURATION_FILE, FRAME_SIZE


def check_for_directory(directory_path: str):
    """
    This function checks if the directory exists, if not it creates the directory
    
    Args:
        directory_path (str): The path of the directory to be checked
    
    Returns:
        bool: True if the directory is created, False if the directory already exists
    """

    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        return True
    return False


def get_bounding_box_size(top, right, bottom, left):
    """This function returns the size of the bounding box
    
    Args:
        top (int): top coordinate of the bounding box
        right (int): right coordinate of the bounding box
        bottom (int): bottom coordinate of the bounding box
        left (int): left coordinate of the bounding box

    Returns:
        int: size of the bounding box
    """
    return (right - left) * (bottom - top)


def count_cameras():
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_configuration_data = json.load(camera_configuration_file)

    return {
        f"{location}_{point}": len(cctv_cameras) if cctv_cameras else 0
        for location, data in camera_configuration_data.items()
        for point, cctv_cameras in data["cctv-cameras"].items()
    }


def map_camera_to_kafka_topic_and_partition():
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_configuration_data = json.load(camera_configuration_file)

    return {
        f"{location}_{point}_{camera}": [f"{location}_{point}", int(camera.split("-")[-1]) - 1]
        for location, data in camera_configuration_data.items()
        for point, cctv_cameras in data["cctv-cameras"].items()
        if cctv_cameras
        for camera in cctv_cameras
    }


def map_camera_to_api_endpoint():
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_configuration_data = json.load(camera_configuration_file)

    return {
        f"{location}_{point}_{camera}": camera_configuration_data[location]['api-endpoint']
        for location, data in camera_configuration_data.items()
        for point, cctv_cameras in data["cctv-cameras"].items()
        if cctv_cameras
        for camera in cctv_cameras
    }


def crop_and_mask_roi(frame, polygon_points):
    polygon_points_np = np.array(polygon_points, dtype=np.int32)

    # Compute the bounding rectangle for the polygon:
    x_min, y_min, w, h = cv2.boundingRect(polygon_points_np)
    x_max, y_max = x_min + w, y_min + h

    # --- 1. Crop the bounding rectangle from the frame ---
    roi_cropped = frame[y_min:y_max, x_min:x_max]

    # --- 2. Create a mask the size of the bounding rectangle ---
    mask = np.zeros((h, w), dtype=np.uint8)

    # --- 3. Shift polygon coords so that (x_min, y_min) is at (0, 0) ---
    shifted_polygon = polygon_points_np - np.array([x_min, y_min])
    # Fill that polygon in the mask:
    cv2.fillPoly(mask, [shifted_polygon], 255)

    # --- 4. Apply the mask to the cropped rectangle ---
    # Everything outside the polygon will become black.
    masked_roi = cv2.bitwise_and(roi_cropped, roi_cropped, mask=mask)

    return masked_roi


def resize_roi_to_area(roi_frame, target_area=FRAME_SIZE):
    """
    Resize a ROI to have approximately the target area (number of pixels)
    without changing its aspect ratio.

    Parameters:
      roi_frame (numpy.ndarray): The cropped ROI image.
      target_area (int): The desired number of pixels (default is 921600).

    Returns:
      numpy.ndarray: The resized ROI image.
    """
    # Get the current dimensions of the ROI
    original_height, original_width = roi_frame.shape[:2]
    current_area = original_width * original_height

    # Compute the scale factor to achieve the target area
    scale_factor = (target_area / current_area) ** 0.5

    # Calculate the new dimensions while preserving aspect ratio
    new_width = int(round(original_width * scale_factor))
    new_height = int(round(original_height * scale_factor))

    # print(f"Original dimensions: {original_width}x{original_height} (area = {current_area})")
    # print(f"Scale factor: {scale_factor:.4f}")
    # print(f"New dimensions: {new_width}x{new_height} (approximate area = {new_width * new_height})")

    # Resize the ROI using the computed dimensions
    resized_roi = cv2.resize(roi_frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    return resized_roi


def load_metadata(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []


def save_metadata(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
