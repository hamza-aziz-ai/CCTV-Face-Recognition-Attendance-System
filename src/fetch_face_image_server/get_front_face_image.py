import cv2
import os
import sys

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from custom_logging import feedback_server_logger
from parameters import DISPLAY_FACE_IMAGE_PATH


DEFAULT_IMAGE = "src/fetch_face_image_server/placeholder.jpg"
# Placeholder image path for non-existing directories
default_image = cv2.imread(DEFAULT_IMAGE)
default_image = cv2.resize(default_image, (256, 256))


# Function to get image IDs and their corresponding images
def get_image_by_id(messages):
    # Process each ID sequentially
    # print(messages)
    results = []
    for entity in messages:
        feedback_server_logger.debug(entity)
        if entity.lower().startswith("error"):
            value = entity.split(": ")[1].strip()
            results.append({"ERROR": value})
            continue

        if entity.lower().startswith("success"):
            value = entity.split(": ")[1].strip()
            results.append({"SUCCESS": value})
            continue

        id_directory = os.path.join(DISPLAY_FACE_IMAGE_PATH, entity)

        # Check if directory exists
        if not os.path.exists(id_directory):
            results.append({entity: default_image})  # Return placeholder.jpg as cv2 image
            continue

        # Collect image file in the directory
        image_file = cv2.imread(f"{id_directory}/front_face.jpg")

        # Check if there are any image files in the directory
        if image_file is None:
            results.append({entity: default_image})
            continue

        # Find the most front-facing image
        image = cv2.resize(image_file, (256, 256))

        # If image is None, use the placeholder image
        if image is None:
            results.append({entity: default_image})
        else:
            results.append({entity: image})

    return results
