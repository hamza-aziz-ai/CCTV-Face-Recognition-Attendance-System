import json
import os
import sys
import time
from datetime import datetime

# import time

import cv2
import base64
import numpy
import pickle

from typing import List, Dict, Tuple, Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import CAMERA_CONFIGURATION_FILE, \
    INSIGHTFACE_HOST, \
    INSIGHTFACE_PORT, \
    MILVUS_HOST, \
    MILVUS_PORT, \
    MILVUS_STAGING_COLLECTION_NAME, \
    FACIAL_RECOGNITION_DATASET_PATH, \
    FACIAL_RECOGNITION_EMBEDDINGS_PATH, \
    FACE_LANDMARKS_PATH, \
    DYNAMIC_DATASET_EMBEDDINGS_PATH
from insightface_face_detection import IFRClient
from milvus_server import create_connection, create_collection, insert_data, delete_collection
from util.generic_utilities import camera_clusters, check_for_directory

from src.dynamic_face_data_collector.postgresql_database_handler import insert_face_data, initialize_database_and_tables, ensure_person_summary_exists, upsert_person_summary

insightface_client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)

# Main database configuration.
DB_CONFIG = {
    'dbname': "TEST_Database",
    'user': os.environ.get("POSTGRES_USER"),
    'password': os.environ.get("POSTGRES_PASSWORD"),
    'host': os.environ.get("POSTGRES_HOST", "localhost"),
    'port': os.environ.get("POSTGRESQL_PORT", "5432")
}

DYNAMIC_DATASET_PATH = "DYNAMIC-FACIAL-RECOGNITION-DATASET.bak"

# Each configured camera's crop group, shared with the collector (util/generic_utilities.camera_clusters)
with open(CAMERA_CONFIGURATION_FILE, "r", encoding="utf-8") as camera_configuration_file:
    flat_map: Dict[str, str] = camera_clusters(json.load(camera_configuration_file))


def get_cluster(camera_name: str) -> str:
    """
    Retrieve the cluster name for a given camera.

    Args:
        camera_name: Identifier of the camera.

    Returns:
        Name of the cluster to which the camera belongs.

    Raises:
        KeyError: If the camera_name is not recognized.
    """
    try:
        cluster = flat_map[camera_name]
        # print(f"Camera '{camera_name}' mapped to cluster '{cluster}'")
        return cluster
    except KeyError as err:
        print(f"Unknown camera: {camera_name}")
        raise KeyError(f"Unknown camera: {camera_name}") from err



def create_embeddings(image_paths: list, store_landmarks: bool, landmarks_path: str, embedding_path: str):
    known_face_encodings = []
    known_face_names = []

    for i, image_path_dictionary in enumerate(image_paths):

        image_paths_list = []
        person_id = None
        for person_id in image_path_dictionary:
            person_id = person_id
            image_paths_list = image_path_dictionary[person_id]

        for image_path in image_paths_list:
            img = cv2.imread(image_path)
            # img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            _, buffer = cv2.imencode(".jpg", img)

            data = base64.b64encode(buffer.tobytes()).decode("ascii")

            faces_data = insightface_client.extract(data=[data], extract_embedding=True, return_landmarks=True)

            print(f"INFO: Creating embeddings for {person_id}: {image_path}")
            for face_data in faces_data['data'][0]['faces']:
                encodings = face_data['vec']
                encodings_array = numpy.array(encodings)

                known_face_encodings.append(encodings_array)
                known_face_names.append(person_id)

                if store_landmarks:
                    # Draw landmarks on the image
                    landmarks = face_data['landmarks']
                    for x, y in landmarks:
                        cv2.circle(img, (int(x), int(y)), 10, (255, 0, 0), -1)

                    # Save the image with landmarks
                    landmarks_folder = f"{landmarks_path}/{person_id}"
                    output_path = os.path.join(landmarks_folder, image_path.split('/')[-1])
                    os.makedirs(landmarks_folder, exist_ok=True)
                    cv2.imwrite(output_path, img)

    # Dump the file encodings with their names into a pickle file
    print("CONCLUDING: Serializing encodings...")
    data = {"names": known_face_names, "encodings": known_face_encodings}

    check_for_directory(embedding_path)
    with open(f"{embedding_path}/dynamic-dataset.pkl", "wb") as embeddings_file:
        embeddings_file.write(pickle.dumps(data))

    print(f"\nINFO: Finished creating embeddings for {len(known_face_encodings)} images and stored in {embedding_path}")

    if store_landmarks:
        print(f"\nINFO: For verification, you can check {landmarks_path} whether embeddings are created correctly if you have opted for saving landmarks.")

    # CONNECTING TO MILVUS SERVER
    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)

    # DELETING THE ALREADY EXISTING COLLECTION
    delete_collection(MILVUS_STAGING_COLLECTION_NAME)

    # CREATING A NEW COLLECTION
    embeddings_collection = create_collection(collection_name=MILVUS_STAGING_COLLECTION_NAME)

    # INSERTING DATA TO NEWLY CREATED COLLECTION
    # entities for milvus database
    entities = [
        known_face_names,
        known_face_encodings
    ]
    insert_data(embeddings_collection, entities)


def insert_data_into_postgresql(files_paths_list: List[Dict[str, List[str]]]):
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                for files_paths_dictionary in files_paths_list:
                    for person_id, file_path_list in files_paths_dictionary.items():
                        # print(file_path_list)
                        for file_path in file_path_list:
                            split_file_path = file_path.split('/')
                            root = os.path.join(split_file_path[0], split_file_path[1], split_file_path[2], split_file_path[3])
                            meta_data_file_path = os.path.join(root, "meta.json")
                            # print(meta_data_file_path)
                            filename = split_file_path[-1]
                            if split_file_path[-2].startswith("maingate"):
                                camera_name = split_file_path[-2]
                                cluster_id = get_cluster(split_file_path[-2])
                            else:
                                cluster_id = split_file_path[-2]
                                camera_name = cluster_id

                            with open(file_path, "rb") as image_file:
                                image_bytes = image_file.read()

                            with open(meta_data_file_path, 'r') as json_file:
                                meta_data: List[Dict[str, Optional[str, float]]] = json.load(json_file)
                            # print(meta_data)
                            for data in meta_data:
                                image_filename: str = data["filename"]
                                if image_filename == filename:
                                    basename: str = image_filename[:-4]
                                    timestamp: datetime = datetime.strptime(basename, "%Y%m%d_%H%M%S_%f")
                                    pupil_distance: float = data["pupil_distance"]
                                    face_matching_score: float = data["match_score"]
                                    break
                            else:
                                # Safety fallback if no match found
                                raise ValueError(f"Metadata for image {filename} not found in {meta_data_file_path}")

                            # print(person_id, filename, pupil_distance, face_matching_score, timestamp)
                            ensure_person_summary_exists(cursor, person_id, timestamp)
                            # Insert the record into the unified table. PostgreSQL will route the data to the correct partition.
                            insert_query = sql.SQL("""
                                INSERT INTO face_images
                                (person_id, image_path, image, camera_name, cluster_id, pupil_distance, face_matching_score, insertion_timestamp)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                            """)
                            cursor.execute(
                                insert_query,
                                (person_id, file_path, image_bytes, camera_name, cluster_id, pupil_distance, face_matching_score, timestamp)
                            )
                            upsert_person_summary(person_id, cursor)
        conn.commit()
    except Exception as error:
        print(f"Error while inserting data: {error}")


if __name__ == "__main__":
    # this will hold [{ 'PERSON_ID': ('path/to/img1.jpg','path/to/img2.jpg') }, …]
    result: List[Dict[str, List[str]]] = []

    for student_id in os.listdir(DYNAMIC_DATASET_PATH):
        student_dir = os.path.join(DYNAMIC_DATASET_PATH, student_id)
        if not os.path.isdir(student_dir):
            continue

        # collect all .jpg paths under this ID (including any nested cluster folders)
        images = []
        for root, _, files in os.walk(student_dir):
            for fn in files:
                # print(fn)
                if fn.lower().endswith('.jpg') or fn.lower().endswith('.jpeg') or fn.lower().endswith('.png'):
                    images.append(os.path.join(root, fn))

        if len(images) >= 1:
            images.sort()  # sorts by filename; adjust if you prefer timestamp order
            result.append({ student_id: [img for img in images] })

    # print(result)
    print(len(result))
    # for i, res in enumerate(result):
    #     print(i, res)
    # initialize_database_and_tables()
    # insert_data_into_postgresql(result)

    create_embeddings(image_paths=result, store_landmarks=True, landmarks_path=FACE_LANDMARKS_PATH, embedding_path=DYNAMIC_DATASET_EMBEDDINGS_PATH)