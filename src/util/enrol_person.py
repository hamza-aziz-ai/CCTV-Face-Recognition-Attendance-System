"""Enrols one person: checks their photos, then adds their embeddings to the primary Milvus collection (D-026).

Usage: python3 src/util/enrol_person.py <folder>
The folder name is the person's ID, and it holds front.jpg, chin_up.jpg, chin_down.jpg, left_30.jpg and right_30.jpg,
plus the same five with _glasses for someone who wears spectacles. Nothing is enrolled unless every photo passes.
"""
import base64
import os
import sys
from pathlib import Path

import cv2

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from enrolment_checks import check_face, check_files, check_not_enrolled, check_same_person
from insightface_face_detection import IFRClient
from milvus_server import create_connection, create_collection, insert_data
from parameters import ENROLMENT_MIN_CONFIDENCE, FACE_MATCHING_TOLERANCE, INSIGHTFACE_HOST, INSIGHTFACE_PORT, \
    METRIC_TYPE, MILVUS_COLLECTION_NAME, MILVUS_HOST, MILVUS_PORT, PUPIL_DISTANCE_THRESHOLD


def extract_faces(client, photo):
    img = cv2.imread(str(photo))
    _, buffer = cv2.imencode(".jpg", img)
    data = base64.b64encode(buffer.tobytes()).decode("ascii")
    faces = client.extract(data=[data], extract_embedding=True, return_landmarks=True)["data"][0]["faces"]
    return faces, cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


def best_match(collection, vector):
    hits = collection.search([vector], "embeddings", {"metric_type": METRIC_TYPE, "params": {"nprobe": 10}}, limit=1,
                             output_fields=["name_id"])[0]
    return (hits[0].entity.get("name_id"), hits[0].distance) if hits else None


def main(folder):
    person_id = folder.name
    photos = {photo.stem: photo for photo in sorted(folder.glob("*.jpg"))}
    problems = check_files(photos)
    if problems:
        return problems

    client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)
    vectors = {}
    for stem, photo in photos.items():
        faces, sharpness = extract_faces(client, photo)
        found = check_face(stem, faces, ENROLMENT_MIN_CONFIDENCE, PUPIL_DISTANCE_THRESHOLD)
        problems += found
        if not found:
            vectors[stem] = faces[0]["vec"]
        print(f"{stem}: {len(faces)} face(s), sharpness {sharpness:.0f}")  # shown only: no pass mark from real data yet
    if problems:
        return problems

    problems += check_same_person(vectors, FACE_MATCHING_TOLERANCE)

    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)
    collection = create_collection(MILVUS_COLLECTION_NAME)
    collection.load()
    if collection.query(f'name_id == "{person_id}"', output_fields=["name_id"], limit=1):
        problems.append(f"{person_id} is already enrolled")
    matches = {stem: match for stem, vector in vectors.items() if (match := best_match(collection, vector))}
    problems += check_not_enrolled(matches, person_id, FACE_MATCHING_TOLERANCE)
    if problems:
        return problems

    insert_data(collection, [[person_id] * len(vectors), list(vectors.values())])
    print(f"Enrolled {person_id} with {len(vectors)} photos.")
    return []


if __name__ == "__main__":
    failures = main(Path(sys.argv[1]).resolve())
    for failure in failures:
        print(f"REJECTED {failure}")
    sys.exit(1 if failures else 0)
