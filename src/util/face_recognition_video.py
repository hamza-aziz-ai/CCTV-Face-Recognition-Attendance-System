import argparse
import cv2
import os
import sys
import numpy as np
from flask import Flask, Response

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import MILVUS_HOST, \
    MILVUS_PORT, \
    MILVUS_COLLECTION_NAME, \
    FACE_MATCHING_TOLERANCE, \
    FRAME_WIDTH, \
    FRAME_HEIGHT, \
    METRIC_TYPE
from milvus_server import create_connection, create_collection, search_embedding
from insightface_face_detection import IFRClient

app = Flask(__name__)
global_stream_url = ""


def draw_rectangle_and_label(frame, x_min, y_min, x_max, y_max, name, similarity, is_match):
    color = (0, 255, 0) if is_match else (0, 0, 255)
    cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 3)
    cv2.putText(
        frame,
        f"{name} ({round(similarity, 3)})",
        (x_min, y_min - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        color,
        2,
    )
    return frame


def inferred_video():
    ifr_client = IFRClient()  # Initialize IFRClient

    # Connect to Milvus
    create_connection(MILVUS_HOST, MILVUS_PORT)

    # Assuming you already have a Milvus collection
    embeddings_collection = create_collection(MILVUS_COLLECTION_NAME)
    embeddings_collection.load()

    # Open the RTSP stream
    cap = cv2.VideoCapture(global_stream_url)
    # cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Unable to open video stream.")
        return

    process_frame = True

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        if process_frame:

            if frame.shape[0] > FRAME_WIDTH or frame.shape[1] > FRAME_HEIGHT:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            # frame = frame[160:1440, 920:1640]
            # print(frame.shape)

            faces_data = ifr_client.plot_bbox(frame)

            for faces in faces_data["data"]:
                for face_data in faces["faces"]:
                    embedding = np.array(face_data["vec"])
                    bbox = face_data["bbox"]
                    x_min, y_min, x_max, y_max = bbox

                    inference_result = search_embedding(embeddings_collection, [embedding])
                    for i, hit in enumerate(inference_result):
                        name_of_person = hit[0].id
                        is_match, percentage_similarity, face_matching_score = None, None, None

                        if METRIC_TYPE == "COSINE":
                            face_matching_score = cosine_similarity = hit[0].distance
                            percentage_similarity = ((cosine_similarity + 1) / 2) * 100
                            is_match = (cosine_similarity >= FACE_MATCHING_TOLERANCE)

                        elif METRIC_TYPE == "L2":
                            face_matching_score = euclidean_distance = hit[0].distance
                            percentage_similarity = (1 - (euclidean_distance / 2)) * 100
                            is_match = (euclidean_distance <= FACE_MATCHING_TOLERANCE)

                        frame = draw_rectangle_and_label(
                            frame,
                            x_min,
                            y_min,
                            x_max,
                            y_max,
                            name_of_person,
                            face_matching_score,
                            is_match,
                        )

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + cv2.imencode('.jpg', frame)[1].tobytes() + b'\r\n')

        process_frame = not process_frame

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


@app.route('/')
def video():
    return Response(inferred_video(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Face Detection")
    parser.add_argument("--stream_url", type=str, default=os.environ.get("RTSP_URL", ""), help="RTSP stream URL")
    args = parser.parse_args()

    global_stream_url = args.stream_url
    app.run(host="0.0.0.0", port=5020)
