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
    # Usage: python3 src/util/upload_embeddings.py <embeddings.pkl>
    upload_embeddings(sys.argv[1])
