import pickle
import os
import sys

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from face_vectors import publish, save
from parameters import FACIAL_RECOGNITION_DATASET_PATH


def upload_embeddings(embeddings_file):
    """Saves a pickle's embeddings into the dataset, one vectors.parquet per person, then publishes a new version of the
    primary collection (D-030). Only the people in the pickle are replaced; everyone else stays."""
    with open(embeddings_file, "rb") as embeddings_file:
        data = pickle.load(embeddings_file)

    by_person = {}
    for name, encoding in zip(data["names"], data["encodings"]):
        by_person.setdefault(name, []).append(encoding)
    for name, encodings in by_person.items():
        folder = os.path.join(FACIAL_RECOGNITION_DATASET_PATH, name)
        os.makedirs(folder, exist_ok=True)
        save(folder, name, encodings)
    publish()


if __name__ == "__main__":
    # Usage: python3 src/util/upload_embeddings.py <embeddings.pkl>
    upload_embeddings(sys.argv[1])
