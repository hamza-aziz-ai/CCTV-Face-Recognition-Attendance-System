"""This module writes the data to a file"""

import os
import cv2
import sys
import json
import re
import urllib.parse
import numpy as np

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import CAMERA_CONFIGURATION_FILE, FRAME_SIZE, CAM_USERNAME, CAM_PASSWORD, CAM_PORT, STREAM_ENDPOINT, KAFKA_TOPIC_PREFIX


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
        f"{KAFKA_TOPIC_PREFIX}{location}_{point}": len(cctv_cameras) if cctv_cameras else 0
        for location, data in camera_configuration_data.items()
        for point, cctv_cameras in data["cctv-cameras"].items()
    }


def map_camera_to_kafka_topic_and_partition():
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_configuration_data = json.load(camera_configuration_file)

    return {
        f"{location}_{point}_{camera}": [f"{KAFKA_TOPIC_PREFIX}{location}_{point}", int(camera.split("-")[-1]) - 1]
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


def camera_stream_url(camera_config):
    """The URL OpenCV opens for a camera: http(s) addresses as they are, otherwise RTSP with the camera's own login,
    port and endpoint, or the site-wide ones from the environment when the camera leaves them null."""
    ip_address = camera_config["ip_address"]
    if ip_address.startswith("http"):
        return ip_address
    port = CAM_PORT if camera_config["port"] is None else camera_config["port"]
    username = CAM_USERNAME if camera_config["username"] is None else camera_config["username"]
    password = CAM_PASSWORD if camera_config["password"] is None else urllib.parse.quote(camera_config["password"])
    endpoint = STREAM_ENDPOINT if camera_config["endpoint"] is None else camera_config["endpoint"]
    return f"rtsp://{username}:{password}@{ip_address}:{port}/{endpoint}"


def crop_and_mask_roi(frame, polygon_points, return_mask=False):
    """The polygon's bounding rectangle, black outside the polygon, and with return_mask also the polygon's mask.
    Raises ValueError, before any OpenCV call, for a region this frame cannot hold: not 3 or more [x, y] points, a point
    outside the frame (a point on its right or bottom edge is fine), or no area. Points are pixels of the snapshot the
    region was drawn on, so a camera whose resolution changed with every point still inside the frame is not caught."""
    polygon_points_np = np.array(polygon_points, dtype=np.int32)
    height, width = frame.shape[:2]
    if polygon_points_np.ndim != 2 or polygon_points_np.shape[0] < 3 or polygon_points_np.shape[1] != 2:
        raise ValueError("needs 3 or more [x, y] points")
    if polygon_points_np.min() < 0 or polygon_points_np[:, 0].max() > width or polygon_points_np[:, 1].max() > height:
        raise ValueError(f"does not fit the {width}x{height} camera picture")
    if cv2.contourArea(polygon_points_np) == 0:
        raise ValueError("has no area")

    # Compute the bounding rectangle for the polygon:
    x_min, y_min, w, h = cv2.boundingRect(polygon_points_np)
    x_max, y_max = x_min + w, y_min + h

    # --- 1. Crop the bounding rectangle from the frame ---
    roi_cropped = frame[y_min:y_max, x_min:x_max]
    if roi_cropped.size == 0:
        raise ValueError(f"does not fit the {width}x{height} camera picture")

    # --- 2. Create a mask the size of the crop: boundingRect is a pixel larger than a frame the polygon reaches the edge of ---
    mask = np.zeros(roi_cropped.shape[:2], dtype=np.uint8)

    # --- 3. Shift polygon coords so that (x_min, y_min) is at (0, 0) ---
    shifted_polygon = polygon_points_np - np.array([x_min, y_min])
    # Fill that polygon in the mask:
    cv2.fillPoly(mask, [shifted_polygon], 255)

    # --- 4. Apply the mask to the cropped rectangle ---
    # Everything outside the polygon will become black.
    masked_roi = cv2.bitwise_and(roi_cropped, roi_cropped, mask=mask)

    return (masked_roi, mask) if return_mask else masked_roi


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
    if current_area == 0:
        raise ValueError("is empty")

    # Compute the scale factor to achieve the target area
    scale_factor = (target_area / current_area) ** 0.5

    # Calculate the new dimensions while preserving aspect ratio
    new_width = int(round(original_width * scale_factor))
    new_height = int(round(original_height * scale_factor))

    # print(f"Original dimensions: {original_width}x{original_height} (area = {current_area})")
    # print(f"Scale factor: {scale_factor:.4f}")
    # print(f"New dimensions: {new_width}x{new_height} (approximate area = {new_width * new_height})")

    # Resize the ROI using the computed dimensions
    resized_roi = cv2.resize(roi_frame, (max(new_width, 1), max(new_height, 1)), interpolation=cv2.INTER_AREA)
    return resized_roi


def load_metadata(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []


def save_metadata(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)


SAFE_CLUSTER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


def camera_clusters(camera_configuration):
    """The face-crop group of every configured camera: its "cluster" key if it has one, so cameras can share a group,
    otherwise its own full name. The collector keeps the best NUMBER_OF_PICTURES crops of a person per group. A group is
    a folder name under the person's folder, so anything but a plain name is refused. Changing a camera's group neither
    moves nor retires the crops already kept under the old one."""
    clusters = {}
    for location, points in camera_configuration.items():
        for point, cameras in (points.get("cctv-cameras") or {}).items():
            for camera, settings in (cameras or {}).items():
                name = f"{location}_{point}_{camera}"
                cluster = (settings or {}).get("cluster") or name
                if not isinstance(cluster, str) or not SAFE_CLUSTER.fullmatch(cluster):
                    raise ValueError(f"camera {name}: cluster {cluster!r} must be letters, digits, '.', '_' or '-', starting with a letter or digit")
                clusters[name] = cluster
    return clusters
