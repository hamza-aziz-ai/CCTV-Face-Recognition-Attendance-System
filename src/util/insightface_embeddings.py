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
    MILVUS_HOST, \
    MILVUS_PORT, \
    MILVUS_COLLECTION_NAME, \
    FACIAL_RECOGNITION_DATASET_PATH, \
    FACIAL_RECOGNITION_EMBEDDINGS_PATH, \
    FACE_LANDMARKS_PATH
from insightface_face_detection import IFRClient
from milvus_server import create_connection, create_collection, insert_data, delete_collection

insightface_client = IFRClient(host="http://localhost", port=18081)


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

    # CONNECTING TO MILVUS SERVER
    create_connection(host="localhost", port=MILVUS_PORT)

    # DELETING THE ALREADY EXISTING COLLECTION
    delete_collection("FACE_EMBEDDINGS")

    # CREATING A NEW COLLECTION
    embeddings_collection = create_collection(collection_name="FACE_EMBEDDINGS")

    # INSERTING DATA TO NEWLY CREATED COLLECTION
    # entities for milvus database
    entities = [
        known_face_names,
        known_face_encodings
    ]
    insert_data(embeddings_collection, entities)


if __name__ == "__main__":
    dataset_folder, embeddings_folder, face_landmarks_folder = None, None, None

    print()
    print("Whose dataset collection are we creating? (Faculties, Students or GRIL)")
    print("Choose from the following:")
    print("========================================================================")
    print("1) Faculties")
    print("2) Students")
    print("3) GRIL")
    print()
    dataset_group = int(input("Enter your choice: "))
    print()
    save_landmarks = input("Do you want to save landmarks? (Y for yes / N for no): ")
    save_landmarks = True if save_landmarks.lower() == "y" else False
    print()

    if dataset_group == 2:
        batch = input("Which batch dataset collection are we creating? (For example, Enter 2021 if admission year is 2021) ")
        enrolled_students = input("Are we creating dataset collection of currently enrolled students? (Y for Yes / N for No) ")
        if enrolled_students.lower() == 'y':
            if batch in ["2021", "2022", "2023", "2024"]:
                dataset_folder = f"{FACIAL_RECOGNITION_DATASET_PATH}/STUDENT_DATASET/CURRENTLY-ENROLLED-STUDENTS/BATCH_{batch}"
                embeddings_folder = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/STUDENT_EMBEDDINGS/CURRENTLY-ENROLLED-STUDENTS/BATCH_{batch}.pkl"
                face_landmarks_folder = f"{FACE_LANDMARKS_PATH}/STUDENT-LANDMARKS/CURRENTLY-ENROLLED-STUDENTS/BATCH_{batch}"
            else:
                print(f"{batch} is not present in currently enrolled batch. Please enter values in [2021, 2022, 2023, 2024]")
                sys.exit(0)
        elif enrolled_students.lower() == 'n':
            confirmation = input(f"There is no point in creating dataset collection of graduated batch {batch}. Do you wish to proceed? (Y for Yes / N for No) ")
            if confirmation.lower() == "y":
                dataset_folder = f"{FACIAL_RECOGNITION_DATASET_PATH}/STUDENT_DATASET/GRADUATED-STUDENTS/BATCH_{batch}"
                embeddings_folder = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/STUDENT_EMBEDDINGS/GRADUATED-STUDENTS/BATCH_{batch}.pkl"
                face_landmarks_folder = f"{FACE_LANDMARKS_PATH}/STUDENT-LANDMARKS/GRADUATED-STUDENTS/BATCH_{batch}"
            else:
                print("Thank you for your confirmation.")
                sys.exit(0)

    elif dataset_group == 1:
        dataset_folder = f"{FACIAL_RECOGNITION_DATASET_PATH}/FACULTY-STAFF-EMPLOYEE_DATASET"
        embeddings_folder = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/FACULTY-STAFF-EMPLOYEE_EMBEDDINGS/Faculty-Staff-Employee.pkl"
        face_landmarks_folder = f"{FACE_LANDMARKS_PATH}/FACULTY-STAFF-EMPLOYEE_LANDMARKS"

    elif dataset_group == 3:
        dataset_folder = f"{FACIAL_RECOGNITION_DATASET_PATH}/GRIL-MEMBERS_DATASET"
        embeddings_folder = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/GRIL-MEMBERS_EMBEDDINGS/GRIL-Members.pkl"
        face_landmarks_folder = f"{FACE_LANDMARKS_PATH}/GRIL-MEMBERS_LANDMARKS"

    else:
        print("Invalid choice.")
        sys.exit(0)

    dataset_folder = "/home/hamza/Downloads/Hamza-Aziz/Hamza Aziz"
    embeddings_folder = "/home/hamza/Downloads/Hamza-Aziz.pkl"

    images_paths = list_image_paths(dataset_folder)

    create_embeddings(images_paths, embeddings_folder, face_landmarks_folder, save_landmarks)
