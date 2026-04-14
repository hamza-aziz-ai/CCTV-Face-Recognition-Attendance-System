"""
This module is created to get the encodings of the faces present in a batch of frames

Author: Hamza Aziz and Kshitij Parashar
"""

import requests
import cv2
import base64
import msgpack
import ujson
import numpy
import os
import sys

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import INSIGHTFACE_HOST, INSIGHTFACE_PORT, ENABLE_FACE_LIVENESS_DETECTION, SAVE_FACE


class IFRClient:

    def __init__(self, host: str = INSIGHTFACE_HOST, port: str = INSIGHTFACE_PORT):
        self.server = f"{host}:{port}"
        self.session = requests.Session()

    def extract(self, data: list,
                mode: str = 'data',
                server: str = None,
                threshold: float = 0.6,
                extract_embedding=True,
                return_face_data=True,
                return_landmarks=True,
                embed_only=False,
                limit_faces=0,
                use_msgpack=True):

        if server is None:
            server = self.server

        extract_uri = f'{server}/extract'

        images = dict()
        if mode == 'data':
            images = dict(data=data)
        elif mode == 'paths':
            images = dict(urls=data)

        req = dict(images=images,
                   threshold=threshold,
                   extract_ga=False,
                   extract_embedding=extract_embedding,
                   return_face_data=return_face_data,
                   return_landmarks=return_landmarks,
                   embed_only=embed_only,  # If set to true, API expects each image to be 112x112 face crop
                   limit_faces=limit_faces,  # Limit maximum number of processed faces, 0 = no limit
                   use_rotation=True,
                   msgpack=use_msgpack,
                   )

        resp = self.session.post(extract_uri, json=req, timeout=120)
        if resp.headers['content-type'] == 'application/x-msgpack':
            content = msgpack.loads(resp.content)
        else:
            content = ujson.loads(resp.content)

        images = content.get('data')

        for im in images:
            status = im.get('status')

            if status != 'ok':
                print(content.get('traceback'))
                break

        return content

    def extract_face_data(self, batch_frames: list, mode='data',
                          threshold=0.6, extract_embeddings=True, return_face_data=True, return_landmarks=False,
                          embed_only=False, limit_faces=0, use_msgpack=True):

        # Initialize an empty batch to store the encoded frame data
        batch_data = []

        for frame in batch_frames:
            # encode each frame in JPEG format
            _, buffer = cv2.imencode(".jpg", frame)
            # get base64 formatted data
            data = base64.b64encode(buffer.tobytes()).decode("ascii")
            batch_data.append(data)

        faces_data = self.extract(
            batch_data, mode=mode, server=self.server, threshold=threshold, extract_embedding=extract_embeddings,
            return_face_data=return_face_data, return_landmarks=return_landmarks, embed_only=embed_only,
            limit_faces=limit_faces, use_msgpack=use_msgpack
        )

        return faces_data

    def batch_face_locations(self, batch_of_frames: list, batch_of_cam_names: list, batch_of_cam_ips: list, mode='data',
                             threshold=0.6, extract_embeddings=True, return_face_data=True, return_landmarks=True,
                             embed_only=False, limit_faces=0, use_msgpack=True):

        # Initialize an empty batch to store the encoded frame data
        batch = []

        for frame in batch_of_frames:
            # encode each frame in JPEG format
            _, buffer = cv2.imencode(".jpg", frame)
            # get base64 formatted data
            data = base64.b64encode(buffer.tobytes()).decode("ascii")
            batch.append(data)

        faces_data = self.extract(batch, mode=mode, server=self.server, threshold=threshold,
                                  extract_embedding=extract_embeddings, return_face_data=return_face_data,
                                  return_landmarks=return_landmarks, embed_only=embed_only, limit_faces=limit_faces,
                                  use_msgpack=use_msgpack)

        batch_encoding_list = []
        batch_frame_list = []
        batch_cam_list = []
        batch_ip_list = []
        batch_bbox_list = []
        batch_face_array_list = []
        batch_landmarks_list = []

        for i, faces in enumerate(faces_data['data']):
            for face_data in faces["faces"]:
                bbox = face_data["bbox"]
                batch_bbox_list.append(bbox)
                encoding = face_data["vec"]
                encoding_array = numpy.array(encoding)
                batch_encoding_list.append(encoding_array)
                batch_frame_list.append(batch_of_frames[i])
                batch_cam_list.append(batch_of_cam_names[i])
                batch_ip_list.append(batch_of_cam_ips[i])
                
                if ENABLE_FACE_LIVENESS_DETECTION or SAVE_FACE:
                    x_min, y_min, x_max, y_max = bbox

                    margin = 0.3
                    # Adjust bounding box with margin
                    width = x_max - x_min
                    height = y_max - y_min
                    margin_x = int(margin * width)
                    margin_y = int(margin * height)

                    x_min = max(0, x_min - margin_x)
                    y_min = max(0, y_min - margin_y)
                    x_max = min(batch_of_frames[i].shape[1], x_max + margin_x)
                    y_max = min(batch_of_frames[i].shape[0], y_max + margin_y)

                    # Ensure the bounding box is square
                    box_width = x_max - x_min
                    box_height = y_max - y_min
                    max_side = max(box_width, box_height)
                    center_x = x_min + box_width // 2
                    center_y = y_min + box_height // 2

                    x_min = max(0, center_x - max_side // 2)
                    y_min = max(0, center_y - max_side // 2)
                    x_max = min(batch_of_frames[i].shape[1], center_x + max_side // 2)
                    y_max = min(batch_of_frames[i].shape[0], center_y + max_side // 2)

                    face_array = batch_of_frames[i][y_min:y_max, x_min:x_max]
                    # face_array = cv2.resize(face_array, (80, 80))
                    batch_face_array_list.append(face_array)
                    batch_landmarks_list.append(face_data["landmarks"])

        return (
            batch_encoding_list,
            batch_bbox_list,
            batch_frame_list,
            batch_cam_list,
            batch_ip_list,
        ) + (
            (batch_face_array_list, batch_landmarks_list)
            if ENABLE_FACE_LIVENESS_DETECTION or SAVE_FACE
            else ()
        )

    def plot_bbox(self, frame: numpy.ndarray, mode='data',
                  threshold=0.6, extract_embeddings=True, return_face_data=True, return_landmarks=False,
                  embed_only=False, limit_faces=0, use_msgpack=True):

        # encode each frame in JPEG format
        _, buffer = cv2.imencode(".jpg", frame)
        # get base64 formatted data
        data = base64.b64encode(buffer.tobytes()).decode("ascii")

        faces_data = self.extract([data], mode=mode, server=self.server, threshold=threshold,
                                  extract_embedding=extract_embeddings, return_face_data=return_face_data,
                                  return_landmarks=return_landmarks, embed_only=embed_only, limit_faces=limit_faces,
                                  use_msgpack=use_msgpack)

        return faces_data
