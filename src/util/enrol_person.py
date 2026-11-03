"""Enrols one person: checks their photos, saves their embeddings next to them, then publishes a new version of the
primary Milvus collection with everyone's saved embeddings (D-026, D-030).

Usage: python3 src/util/enrol_person.py <folder>
The folder name is the person's ID, and it holds front.jpg, chin_up.jpg, chin_down.jpg, left_30.jpg and right_30.jpg,
plus the same five with _glasses for someone who wears spectacles. Nothing is enrolled unless every photo passes.
"""
import base64
import os
import sys
from pathlib import Path

import cv2
import numpy as np

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from enrolment_checks import check_face, check_files, check_not_enrolled, check_photo_file, check_poses, \
    check_same_person, check_sharpness
from insightface_face_detection import IFRClient
from face_vectors import publish, save
from milvus_server import create_connection, create_collection
from parameters import ENROLMENT_MAX_FRONT_TURN, ENROLMENT_MAX_PHOTO_BYTES, ENROLMENT_MIN_CONFIDENCE, \
    ENROLMENT_MIN_SHARPNESS, ENROLMENT_MIN_SHORT_SIDE, ENROLMENT_MIN_TILT, ENROLMENT_MIN_TURN, FACE_MATCHING_TOLERANCE, \
    INSIGHTFACE_HOST, INSIGHTFACE_PORT, METRIC_TYPE, MILVUS_COLLECTION_NAME, MILVUS_HOST, MILVUS_PORT, \
    PUPIL_DISTANCE_THRESHOLD


def face_sharpness(img, bbox):
    """Laplacian variance of the face scaled to 112 x 112, so the score does not depend on the photo's size."""
    x1, y1, x2, y2 = (max(0, int(v)) for v in bbox)
    crop = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY) if y2 > y1 and x2 > x1 else None
    return cv2.Laplacian(cv2.resize(crop, (112, 112)), cv2.CV_64F).var() if crop is not None else 0.0


def extract_faces(client, img):
    _, buffer = cv2.imencode(".jpg", img)
    data = base64.b64encode(buffer.tobytes()).decode("ascii")
    return client.extract(data=[data], extract_embedding=True, return_landmarks=True)["data"][0]["faces"]


def check_photos(client, photos):
    """{stem: JPEG bytes} to ({stem: embedding}, problems): every photo check of D-026 and 8c in one place, for the
    command line and the enrolment API."""
    problems = check_files(photos)
    if problems:
        return {}, problems
    vectors, landmarks = {}, {}
    for stem, data in photos.items():
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        short_side = min(img.shape[:2]) if img is not None else 0
        found = check_photo_file(stem, data, ENROLMENT_MAX_PHOTO_BYTES, short_side, ENROLMENT_MIN_SHORT_SIDE)
        if not found:
            faces = extract_faces(client, img)
            found = check_face(stem, faces, ENROLMENT_MIN_CONFIDENCE, PUPIL_DISTANCE_THRESHOLD)
            if not found:
                found = check_sharpness(stem, face_sharpness(img, faces[0]["bbox"]), ENROLMENT_MIN_SHARPNESS)
                vectors[stem], landmarks[stem] = faces[0]["vec"], faces[0]["landmarks"]
        problems += found
    problems += check_poses(landmarks, ENROLMENT_MIN_TURN, ENROLMENT_MIN_TILT, ENROLMENT_MAX_FRONT_TURN)
    if problems:
        return {}, problems
    return vectors, check_same_person(vectors, FACE_MATCHING_TOLERANCE)


def best_match(collection, vector):
    hits = collection.search([vector], "embeddings", {"metric_type": METRIC_TYPE, "params": {"nprobe": 10}}, limit=1,
                             output_fields=["name_id"])[0]
    return (hits[0].entity.get("name_id"), hits[0].distance) if hits else None


def vectors_for(folder):
    """The embedding of each photo in the folder, keyed by pose, and the problems that stop enrolment."""
    photos = {photo.stem: photo.read_bytes() for photo in sorted(folder.glob("*.jpg"))}
    return check_photos(IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT), photos)


def main(folder):
    person_id = folder.name
    vectors, problems = vectors_for(folder)
    if not vectors:
        return problems

    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)
    collection = create_collection(MILVUS_COLLECTION_NAME)
    collection.load()
    if collection.query(f'name_id == "{person_id}"', output_fields=["name_id"], limit=1):
        problems.append(f"{person_id} is already enrolled")
    matches = {stem: match for stem, vector in vectors.items() if (match := best_match(collection, vector))}
    problems += check_not_enrolled(matches, person_id, FACE_MATCHING_TOLERANCE)
    if problems:
        return problems

    save(folder, person_id, vectors.values())
    publish(folder.parent)
    print(f"Enrolled {person_id} with {len(vectors)} photos. Version the dataset: dvc add {folder.parent.name} && dvc push")
    return []


if __name__ == "__main__":
    failures = main(Path(sys.argv[1]).resolve())
    for failure in failures:
        print(f"REJECTED {failure}")
    sys.exit(1 if failures else 0)
