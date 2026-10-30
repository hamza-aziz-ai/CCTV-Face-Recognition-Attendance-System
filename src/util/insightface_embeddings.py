import os
import sys
# import time

import cv2
import base64
import numpy
import pickle

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import INSIGHTFACE_HOST, \
    INSIGHTFACE_PORT, \
    FACIAL_RECOGNITION_DATASET_PATH, \
    FACIAL_RECOGNITION_EMBEDDINGS_PATH, \
    FACE_LANDMARKS_PATH
from insightface_face_detection import IFRClient

insightface_client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)


def list_image_paths(directory: str):
    image_extensions = ['.jpg', '.jpeg', '.png']

    image_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            _, extension = os.path.splitext(file)
            if extension.lower() in image_extensions:
                image_path = os.path.join(root, file)
                image_paths.append(image_path)

    return image_paths


def create_embeddings(image_paths: list, embedding_path: str, landmarks_path: str, store_landmarks: bool):
    known_face_encodings = []
    known_face_names = []

    for i, image_path in enumerate(image_paths):
        name = image_path.split('/')[-2]
        image_name = image_path.split('/')[-1]
        print(f"INFO: Processing image {i + 1}/{len(image_paths)}...")

        img = cv2.imread(image_path)
        # img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        _, buffer = cv2.imencode(".jpg", img)

        data = base64.b64encode(buffer.tobytes()).decode("ascii")

        faces_data = insightface_client.extract(data=[data], extract_embedding=True, return_landmarks=True)

        print(f"INFO: Creating embeddings for {name}")
        for face_data in faces_data['data'][0]['faces']:
            encodings = face_data['vec']
            encodings_array = numpy.array(encodings)

            known_face_encodings.append(encodings_array)
            known_face_names.append(name)

            if store_landmarks:
                # Draw landmarks on the image
                landmarks = face_data['landmarks']
                for x, y in landmarks:
                    cv2.circle(img, (int(x), int(y)), 10, (255, 0, 0), -1)

                # Save the image with landmarks
                landmarks_folder = f"{landmarks_path}/{name}"
                output_path = os.path.join(landmarks_folder, image_name)
                os.makedirs(landmarks_folder, exist_ok=True)
                cv2.imwrite(output_path, img)

    # Dump the file encodings with their names into a pickle file
    # print("CONCLUDING: Serializing encodings...")
    data = {"names": known_face_names, "encodings": known_face_encodings}

    with open(f"{embedding_path}", "wb") as embeddings_file:
        embeddings_file.write(pickle.dumps(data))

    print(f"\nINFO: Finished creating embeddings for {len(known_face_encodings)} images and stored in {embedding_path}")

    if store_landmarks:
        print(f"\nINFO: For verification, you can check {landmarks_path} whether embeddings are created correctly if you have opted for saving landmarks.")


if __name__ == "__main__":
    # Usage: python3 src/util/insightface_embeddings.py <dataset_folder> <embeddings.pkl> [--landmarks]
    dataset_folder, embeddings_file = sys.argv[1:3]
    create_embeddings(list_image_paths(dataset_folder), embeddings_file, FACE_LANDMARKS_PATH, "--landmarks" in sys.argv)
