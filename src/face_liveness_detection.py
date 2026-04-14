"""
This module is created to make an API call to the Face Liveness Detection Server.

Date: 12 December 2023
Author: Hamza Aziz
"""

import base64
from typing import List

import cv2
import numpy as np
import requests
from requests.exceptions import RequestException

from parameters import FACE_LIVENESS_DETECTION_HOST, FACE_LIVENESS_DETECTION_PORT

# URL of the FastAPI endpoint
api_url = f"{FACE_LIVENESS_DETECTION_HOST}:{FACE_LIVENESS_DETECTION_PORT}/liveness_detection/"


def face_liveness_detection(person_id: str, faces: List[np.ndarray]):
    try:
        # Encode NumPy array to base64 string
        batch_of_faces = []
        for face in faces:
            # encode each frame in JPEG format
            _, buffer = cv2.imencode(".jpg", face)
            # get base64 formatted data
            data = base64.b64encode(buffer.tobytes()).decode("ascii")
            batch_of_faces.append(data)

        # Make a POST request to the FastAPI endpoint
        # print(person_id, batch_of_faces)
        data = {"person_id": person_id, "faces": batch_of_faces}
        response = requests.post(
            url=api_url,
            json=data
        )

        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx and 5xx)
        person_face_liveness = response.json()

        # print(batch_result)
        return person_face_liveness

    except Exception as error:
        # print(error)
        raise RequestException(f"Request error: {str(error)}")

