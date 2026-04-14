import pickle
import os
import sys

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION_NAME, FACIAL_RECOGNITION_EMBEDDINGS_PATH
from milvus_server import create_connection, create_collection, insert_data, delete_collection

def upload_embeddings(embeddings_file):
    with open(embeddings_file, "rb") as embeddings_file:
        data = pickle.load(embeddings_file)

    # data = pickle.loads(open(embeddings_file, "rb").read())

    known_face_encodings = data["encodings"]
    known_face_names = data["names"]

    # CONNECTING TO MILVUS SERVER
    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)

    # DELETING THE ALREADY EXISTING COLLECTION
    delete_collection(MILVUS_COLLECTION_NAME)

    # CREATING A NEW COLLECTION
    embeddings_collection = create_collection(collection_name=MILVUS_COLLECTION_NAME)

    # INSERTING DATA TO NEWLY CREATED COLLECTION
    # entities for milvus database
    entities = [
        known_face_names,
        known_face_encodings
    ]

    insert_data(embeddings_collection, entities)

if __name__ == "__main__":
    embeddings_path = None

    print()
    print("Whose face embeddings are we uploading? (Faculties, Students or GRIL)")
    print("Choose from the following:")
    print("========================================================================")
    print("1) Faculties")
    print("2) Students")
    print("3) GRIL")
    print()
    dataset_group = int(input("Enter your choice: "))
    print()

    if dataset_group == 2:
        batch = input("Which batch face embeddings are we uploading? (For example, Enter 2021 if admission year is 2021) ")
        enrolled_students = input("Are we uploading face embeddings of currently enrolled students? (Y for Yes / N for No) ")
        if enrolled_students.lower() == 'y':
            if batch in ["2021", "2022", "2023", "2024"]:
                embeddings_path = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/STUDENT_EMBEDDINGS/CURRENTLY-ENROLLED-STUDENTS/BATCH_{batch}.pkl"
            else:
                print(f"{batch} is not present in currently enrolled batch. Please enter values in [2021, 2022, 2023, 2024]")
                sys.exit(0)
        elif enrolled_students.lower() == 'n':
            confirmation = input(f"There is no point in uploading face embeddings of graduated batch {batch}. Do you wish to proceed? (Y for Yes / N for No) ")
            if confirmation.lower() == "y":
                embeddings_path = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/STUDENT_EMBEDDINGS/GRADUATED-STUDENTS/BATCH_{batch}.pkl"
            else:
                print("Thank you for your confirmation.")
                sys.exit(0)

    elif dataset_group == 1:
        embeddings_path = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/FACULTY-STAFF-EMPLOYEE_EMBEDDINGS/Faculty-Staff-Employee.pkl"

    elif dataset_group == 3:
        embeddings_path = f"{FACIAL_RECOGNITION_EMBEDDINGS_PATH}/GRIL-MEMBERS_EMBEDDINGS/GRIL-Members.pkl"

    else:
        print("Invalid choice.")
        sys.exit(0)

    upload_embeddings(embeddings_path)

