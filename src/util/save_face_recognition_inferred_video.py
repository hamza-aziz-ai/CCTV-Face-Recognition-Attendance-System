import argparse
import cv2
import os
import sys
import numpy as np

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import (
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION_NAME,
    FACE_MATCHING_TOLERANCE,
    METRIC_TYPE
)

from milvus_server import create_connection, create_collection, search_embedding
from insightface_face_detection import IFRClient

base_path = os.path.abspath(os.path.join(current, ".."))


def draw_rectangle_and_label(
        frame: np.ndarray,
        x_min: int,
        y_min: int,
        x_max: int,
        y_max: int,
        person_id: str,
        is_match: bool,
        face_distance: float = None,
        percentage_similarity: float = None
):
    color = (0, 255, 0) if is_match else (0, 0, 255)
    text = ""
    if percentage_similarity is not None:
        text = f"{person_id} ({round(percentage_similarity, 2)}%)"
    elif face_distance is not None:
        if METRIC_TYPE == "COSINE":
            text = f"{person_id} (COSINE Similarity: {round(percentage_similarity, 3)})"
        elif METRIC_TYPE == "L2":
            text = f"{person_id} (EUCLIDEAN Distance: {round(percentage_similarity, 3)})"

    cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 3)
    cv2.putText(
        frame,
        text,
        (x_min, y_min - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        color,
        2,
    )
    return frame


def process_video(stream_url: str, crop_frame: bool = False, save_with_score: bool = None, save_with_percentage: bool = None):
    ifr_client = IFRClient()
    create_connection(MILVUS_HOST, MILVUS_PORT)
    embeddings_collection = create_collection(MILVUS_COLLECTION_NAME)
    embeddings_collection.load()

    cap = cv2.VideoCapture(stream_url)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # print(f"Frame width: {frame_width}, Frame height: {frame_height}")
    file_name = os.path.splitext(os.path.basename(stream_url))[0]

    if not cap.isOpened():
        print("Error: Unable to open video stream.")
        return

    video_filename = ""
    if save_with_score:
        video_filename = os.path.join(base_path, "INFERRED-VIDEOS", METRIC_TYPE, f"{file_name}__FACE-MATCHING-SCORE.avi")
    elif save_with_percentage:
        video_filename = os.path.join(base_path, "INFERRED-VIDEOS", METRIC_TYPE, f"{file_name}__PERCENTAGE_SIMILARITY.avi")

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(video_filename, fourcc, 30.0, (frame_width, frame_height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if crop_frame:
            x_min = 1000
            x_max = 2000
            y_min = 0
            y_max = 1440
            frame = frame[y_min:y_max, x_min:x_max]

        faces_data = ifr_client.plot_bbox(frame)

        for faces in faces_data["data"]:
            for face_data in faces["faces"]:
                embedding = np.array(face_data["vec"])
                bbox = face_data["bbox"]
                x_min, y_min, x_max, y_max = bbox

                inference_result = search_embedding(embeddings_collection, [embedding])
                for hit in inference_result:
                    person_id = hit[0].id
                    is_match = None
                    score = None
                    percentage_similarity = None

                    if METRIC_TYPE == "COSINE":
                        score = cosine_similarity = hit[0].distance
                        percentage_similarity = ((cosine_similarity + 1) / 2) * 100
                        is_match = (cosine_similarity >= FACE_MATCHING_TOLERANCE)
                    elif METRIC_TYPE == "L2":
                        score = euclidean_distance = hit[0].distance
                        percentage_similarity = (1 - (euclidean_distance / 2)) * 100
                        is_match = (euclidean_distance <= FACE_MATCHING_TOLERANCE)

                    if save_with_score:
                        frame = draw_rectangle_and_label(frame, x_min, y_min, x_max, y_max, person_id, is_match, score)
                    elif save_with_percentage:
                        frame = draw_rectangle_and_label(frame, x_min, y_min, x_max, y_max, person_id, is_match, percentage_similarity)

        out.write(frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print("Video processing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Face Recognition and Video Processing")
    parser.add_argument("--save_with_score", type=bool, default=True, help="Save inferred video with face matching score")
    parser.add_argument("--save_with_percentage", type=bool, default=True, help="Save inferred video with face matching percentage")
    parser.add_argument("--stream_url", type=str, default=False, help="source video path (camera_index for local camera, RTSP/HTTP URL for network camera, file_path for recorded video)")
    args = parser.parse_args()

    process_video(args.stream_url, args.save_with_score, args.save_with_percentage)
