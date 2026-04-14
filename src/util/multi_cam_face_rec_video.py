import argparse
import cv2
import os
import sys
import threading
import numpy as np
from flask import Flask, Response
from queue import Queue

# Add parent path for imports
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION_NAME, FACE_MATCHING_TOLERANCE, METRIC_TYPE
from milvus_server import create_connection, create_collection, search_embedding
from insightface_face_detection import IFRClient

app = Flask(__name__)
stream_urls = ["", "", ""]


class StreamReader(threading.Thread):
    def __init__(self, stream_url):
        super().__init__()
        self.stream_url = stream_url
        self.cap = cv2.VideoCapture(self.stream_url)
        self.frame = None
        self.lock = threading.Lock()
        self.running = True

    def run(self):
        while self.running:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.frame = frame

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        self.cap.release()


def draw_rectangle_and_label(frame, x_min, y_min, x_max, y_max, name, similarity, is_match):
    color = (0, 255, 0) if is_match else (0, 0, 255)
    cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 2)
    label = f"{name} ({round(similarity, 2)})"
    cv2.putText(frame, label, (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def tiled_stream(stream_threads):
    ifr_client = IFRClient()
    create_connection(MILVUS_HOST, MILVUS_PORT)
    collection = create_collection(MILVUS_COLLECTION_NAME)
    collection.load()

    while True:
        frames = []
        for reader in stream_threads:
            frame = reader.get_frame()
            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)  # fallback frame
            else:
                frame = cv2.resize(frame, (1280, 720))
                faces_data = ifr_client.plot_bbox(frame)
                for faces in faces_data["data"]:
                    for face_data in faces["faces"]:
                        embedding = np.array(face_data["vec"])
                        x_min, y_min, x_max, y_max = face_data["bbox"]

                        results = search_embedding(collection, [embedding])
                        for hit in results:
                            name = hit[0].id
                            similarity = hit[0].distance
                            is_match = False

                            if METRIC_TYPE == "COSINE":
                                is_match = hit[0].distance >= FACE_MATCHING_TOLERANCE
                            elif METRIC_TYPE == "L2":
                                similarity = (1 - (hit[0].distance / 2)) * 100
                                is_match = hit[0].distance <= FACE_MATCHING_TOLERANCE

                            frame = draw_rectangle_and_label(frame, x_min, y_min, x_max, y_max, name, similarity, is_match)

            frames.append(frame)

        # Match dimensions by padding
        max_height = max(f.shape[0] for f in frames)
        max_width = max(f.shape[1] for f in frames)

        padded_frames = []
        for f in frames:
            h, w = f.shape[:2]
            padded = cv2.copyMakeBorder(f, 0, max_height - h, 0, max_width - w, cv2.BORDER_CONSTANT, value=(0, 0, 0))
            padded_frames.append(padded)

        while len(padded_frames) < 4:
            padded_frames.append(np.zeros((max_height, max_width, 3), dtype=np.uint8))

        top = np.hstack(padded_frames[:2])
        bottom = np.hstack(padded_frames[2:])
        tiled_frame = np.vstack([top, bottom])

        ret, jpeg = cv2.imencode('.jpg', tiled_frame)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')


@app.route('/')
def tiled():
    return Response(tiled_stream(stream_readers), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tiled Face Detection Stream Viewer")
    parser.add_argument("--stream1_url", type=str, default="src/test_videos/cam-1.avi")
    parser.add_argument("--stream2_url", type=str, default="src/test_videos/cam-2.avi")
    parser.add_argument("--stream3_url", type=str, default="src/test_videos/cam-3.avi")
    args = parser.parse_args()

    stream_urls[0] = args.stream1_url
    stream_urls[1] = args.stream2_url
    stream_urls[2] = args.stream3_url

    # Initialize and start stream threads
    stream_readers = [StreamReader(url) for url in stream_urls]
    for reader in stream_readers:
        reader.start()

    try:
        app.run(host="0.0.0.0", port=5030, debug=True)
    finally:
        for reader in stream_readers:
            reader.stop()
