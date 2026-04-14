import os
import argparse
import time

import cv2
import numpy as np
from flask import Flask, Response

from face_liveness_detection import face_liveness_detection
from src.insightface_face_detection import IFRClient
from milvus_server import create_connection, create_collection, search_embedding
from parameters import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION_NAME, FACE_MATCHING_TOLERANCE

app = Flask(__name__)
global_stream_url = ""


def inferred_video():
    ifr_client = IFRClient()  # Initialize IFRClient

    # Connect to Milvus
    create_connection(MILVUS_HOST, MILVUS_PORT)

    # Assuming you already have a Milvus collection
    embeddings_collection = create_collection(MILVUS_COLLECTION_NAME)

    # Open the RTSP stream
    cap = cv2.VideoCapture(global_stream_url)

    if not cap.isOpened():
        print("Error: Unable to open video stream.")
        return

    frame_count = 0
    real_count = 0
    fake_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        resized_frame = cv2.resize(frame, (640, 360))
        faces_data = ifr_client.plot_bbox(resized_frame)

        for faces in faces_data["data"]:
            for face_data in faces["faces"]:
                embedding = np.array(face_data["vec"])
                bbox = face_data["bbox"]

                inference_result = search_embedding(embeddings_collection, [embedding])
                for i, hit in enumerate(inference_result):
                    name_of_person, face_distance = hit[0].id, hit[0].distance

                    if face_distance <= FACE_MATCHING_TOLERANCE:
                        frame_count += 1
                        x_min, y_min, x_max, y_max = bbox
                        margin = 0.3
                        # Adjust bounding box with margin
                        width = x_max - x_min
                        height = y_max - y_min
                        margin_x = int(margin * width)
                        margin_y = int(margin * height)

                        x_min = max(0, x_min - margin_x)
                        y_min = max(0, y_min - margin_y)
                        x_max = min(frame.shape[1], x_max + margin_x)
                        y_max = min(frame.shape[0], y_max + margin_y)

                        # Ensure the bounding box is square
                        box_width = x_max - x_min
                        box_height = y_max - y_min
                        max_side = max(box_width, box_height)
                        center_x = x_min + box_width // 2
                        center_y = y_min + box_height // 2

                        x_min = max(0, center_x - max_side // 2)
                        y_min = max(0, center_y - max_side // 2)
                        x_max = min(frame.shape[1], center_x + max_side // 2)
                        y_max = min(frame.shape[0], center_y + max_side // 2)

                        face_crop = resized_frame[y_min:y_max, x_min:x_max]
                        face_crop = cv2.resize(face_crop, (80, 80))
                        # face_crop = cv2.GaussianBlur(face_crop, (5, 5), sigmaX=0, sigmaY=0)

                        face_liveness_start_time = time.time()
                        person_face_liveness = face_liveness_detection(name_of_person, [face_crop])
                        face_liveness_end_time = time.time()
                        face_liveness_total_time = face_liveness_end_time - face_liveness_start_time
                        print(
                            f"Time taken to perform face liveness detection on the batch of faces is {face_liveness_total_time:.3f} seconds"
                        )
                        # print(person_face_liveness)

                        if "error" in person_face_liveness:
                            print(
                                f"Error while detecting face liveness for {name_of_person}: {person_face_liveness['error']}"
                            )
                        else:
                            liveness_counter = person_face_liveness[name_of_person]
                            real_face_count = liveness_counter.get("Real Face", 0)
                            fake_face_count = liveness_counter.get("Spoof Face", 0)
                            # print(real_count > fake_count)
                            if real_face_count > fake_face_count:
                                real_count += 1
                                cv2.rectangle(resized_frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
                                cv2.putText(resized_frame, f"{name_of_person} ({round(face_distance, 3)})", (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                            else:
                                fake_count += 1
                                cv2.rectangle(resized_frame, (x_min, y_min), (x_max, y_max), (0, 0, 255), 2)
                                cv2.putText(resized_frame, f"Spoofing Attempt", (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    # else:
                    #     cv2.rectangle(resized_frame, (x_min, y_min), (x_max, y_max), (0, 0, 255), 3)
                    #     cv2.putText(resized_frame, f"POSSIBLY: {name_of_person} ({round(face_distance, 3)})", (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

        if frame_count == 200:
            print(f"Out of {frame_count} frames, {real_count} frames were labeled as real face and {fake_count} frames were labeled as fake face.")
            frame_count = 0
            real_count = 0
            fake_count = 0

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + cv2.imencode('.jpg', resized_frame)[1].tobytes() + b'\r\n')

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
    app.run(host="0.0.0.0", port=5080)
