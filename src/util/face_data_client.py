#!/usr/bin/env python3
"""
face_data_client.py

Client module to send face records in batch (as JSON) to the
Dynamic Face Data Collector API (/faces endpoint).

Usage:
    from face_data_client import send_faces_via_api
    send_faces_via_api(cropped_faces_data, api_url='http://localhost:8000')
"""
import base64
import threading
import os
import sys
from typing import Dict, List, Tuple
from queue import Queue
import json
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import requests

# Relative import fix
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from custom_logging import dynamic_face_data_collector_logger as logger
from parameters import DYNAMIC_FACE_DATA_COLLECTOR_TOKEN


# Global, fixed‑size executor
_executor = ThreadPoolExecutor(
    max_workers=16,
    thread_name_prefix="face-poster",
)
# ponytail: 16 batches sending and 16 waiting; past that a batch is dropped and counted, so a slow or unreachable collector
# never grows memory. Crops only refresh the gallery: an on-disk queue like the attendance sender's is not worth it here
_slots = threading.BoundedSemaphore(32)
dropped = 0



def _handle_future(future):
    err = future.exception()
    if err:
        logger.error(f"Face submission task error: {err}")


def send_faces_via_api(
    cropped_faces_data: Dict[str, List[Tuple[np.ndarray, float, str, List[Tuple[int, int]]]]],
    api_url: str = 'http://localhost:8000'
) -> bool:
    """
    Batch-send face records to the new JSON-based API. Returns True only when every crop was kept.

    Args:
        cropped_faces_data: dict mapping person_id -> list of records
            Each record: (face_crop (numpy array), match_score, camera_name, landmarks)
        api_url: base URL of the FastAPI server (without trailing slash)
    """
    endpoint = f"{api_url}/faces"
    payload = []

    for person_id, records in cropped_faces_data.items():
        for face_crop, match_score, camera_name, landmarks in records:
            # Encode face image to JPEG and then base64
            success, buffer = cv2.imencode('.jpg', face_crop)
            if not success:
                logger.error(f"JPEG encoding failed for {person_id}@{camera_name}")
                continue

            image_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')

            # Append the face record to payload list
            payload.append({
                "person_id": person_id,
                "camera_name": camera_name,
                "match_score": match_score,
                "landmarks": landmarks,
                "image_base64": image_base64
            })

    # Submit the list of face records in a single JSON POST
    if not payload:
        return True
    headers = {}
    if DYNAMIC_FACE_DATA_COLLECTOR_TOKEN:
        # An edge node's token goes only over TLS, checked by requests (REQUESTS_CA_BUNDLE for the site's own certificate)
        if not endpoint.startswith("https://"):
            logger.error(f"Face crops not sent: DYNAMIC_FACE_DATA_COLLECTOR_TOKEN is set, so {endpoint} must be https://")
            return False
        headers["Authorization"] = f"Bearer {DYNAMIC_FACE_DATA_COLLECTOR_TOKEN}"
    try:
        size_bytes = len(json.dumps(payload).encode('utf-8'))
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        logger.debug(f"Sending {len(payload)} faces ({size_bytes / 1024:.3f} KB) to {endpoint}")
    except requests.RequestException as e:
        logger.error(f"Error submitting {len(payload)} face crops to {endpoint}: {e}")
        return False
    # 207 passes raise_for_status, but some crops were not kept
    if response.status_code == 207:
        try:
            failures = response.json().get("failures", [])
        except ValueError:
            failures = []
        logger.error(f"{len(failures) or 'Some'} of {len(payload)} face crops were not kept: {failures[:3]}")
        return False
    return True


def submit_faces_async(cropped_faces_data, api_url):
    """
    Non‑blocking: queues the batch for the 16 senders, or drops it when 32 are already in hand.
    """
    global dropped
    if not _slots.acquire(blocking=False):
        dropped += 1
        if dropped == 1 or dropped % 100 == 0:
            logger.error(f"Face crop sender is full (collector slow or unreachable): {dropped} batches dropped so far")
        return False
    future = _executor.submit(send_faces_via_api, cropped_faces_data, api_url)
    future.add_done_callback(lambda done: (_slots.release(), _handle_future(done)))
    return True

# def submit_faces_async(cropped_faces_data, api_url):
#     def task():
#         try:
#             send_faces_via_api(cropped_faces_data, api_url)
#         except Exception as e:
#             logger.error(f"Async face data submission failed: {e}")
#
#     threading.Thread(target=task, daemon=True).start()
