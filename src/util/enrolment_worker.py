"""Enrolment worker (8c, D-048): checks each job the enrolment API accepted for checking, then publishes or rejects it.

Accepted: the photos move to persons/<person_id>/ in the client's bucket, the vectors are saved beside the dataset as
vectors.parquet (D-030) and Milvus is rebuilt by face_vectors.publish, one publish at a time across workers. Rejected or
expired: the photos are deleted at once and only the reasons stay. Deletions the API records (8e) run here too, as soon
as they are seen, and attendance records' camera pictures are cleared hourly once due (enrolment_deletion.py). Runs in the producer-consumer image, which has the
InsightFace client, OpenCV and Milvus already: python3 src/util/enrolment_worker.py
"""
import json
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras

current = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [os.path.dirname(current), current]
from custom_logging import api_logger as logger  # noqa: E402
from enrol_person import best_match, check_photos  # noqa: E402
from enrolment_checks import as_problems  # noqa: E402
import enrolment_deletion  # noqa: E402
from enrolment_store import Store  # noqa: E402
from face_vectors import forget, publish, save  # noqa: E402
from insightface_face_detection import IFRClient  # noqa: E402
from milvus_server import create_collection, create_connection  # noqa: E402
from parameters import ENROLMENT_PENDING_HOURS, FACE_MATCHING_TOLERANCE, FACIAL_RECOGNITION_DATASET_PATH, INSIGHTFACE_HOST, \
    INSIGHTFACE_PORT, MILVUS_COLLECTION_NAME, MILVUS_HOST, MILVUS_PORT, POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, \
    postgres_login  # noqa: E402

PUBLISH_LOCK = 8048  # a PostgreSQL advisory lock: publish rebuilds the whole collection, so two at once would race
IDLE_SECONDS = 2
FRAME_CHECK_SECONDS = 3600


def already_enrolled(collection, person_id, vectors):
    """Matches to someone else, worded without their ID: the operator needs to know, not who (data minimisation)."""
    lines = []
    for stem, vector in vectors.items():
        match = best_match(collection, vector)
        if match and match[0] != person_id and match[1] >= FACE_MATCHING_TOLERANCE:
            logger.warning(f"Enrolment of {person_id}: {stem} matches enrolled {match[0]} ({match[1]:.2f})")
            lines.append(f"{stem}: matches someone already enrolled ({match[1]:.2f})")
    return lines


def connect():
    user, password = postgres_login()
    return psycopg2.connect(dbname=POSTGRESQL_DATABASE, user=user, password=password, host=POSTGRESQL_HOST, port=POSTGRESQL_PORT,
                            cursor_factory=psycopg2.extras.RealDictCursor)


def expire(conn, store):
    with conn, conn.cursor() as db:
        db.execute("""UPDATE enrolment_jobs SET status = 'expired', finished_at = now(),
                             problems = '[{"pose": null, "problem": "not checked within the time limit; retake the photos", "code": "expired"}]'
                      WHERE status = 'pending' AND created_at < now() - make_interval(hours => %s) RETURNING id, poses""",
                   (ENROLMENT_PENDING_HOURS,))
        jobs = db.fetchall()
    for job in jobs:
        store.delete([f"jobs/{job['id']}/{pose}.jpg" for pose in job["poses"]])
        logger.warning(f"Enrolment job {job['id']} expired; photos deleted")


def finish(db, job_id, status, problems=()):
    db.execute("UPDATE enrolment_jobs SET status = %s, problems = %s, finished_at = now() WHERE id = %s",
               (status, json.dumps(list(problems)), job_id))


def process(conn, store, client, collection_source, dataset=FACIAL_RECOGNITION_DATASET_PATH) -> bool:
    """Checks the oldest pending job. Returns whether there was one. The job's row stays locked while it is checked, so a
    second worker skips it, and a withdrawal waits until the outcome is written."""
    with conn, conn.cursor() as db:
        db.execute("SELECT id, person_id, poses FROM enrolment_jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED")
        job = db.fetchone()
        if not job:
            return False
        job_id, person_id, poses = str(job["id"]), job["person_id"], job["poses"]
        keys = [f"jobs/{job_id}/{pose}.jpg" for pose in poses]
        photos = {pose: store.get(key) for pose, key in zip(poses, keys)}
        vectors, lines = check_photos(client, photos)
        if not lines:
            lines = already_enrolled(collection_source(), person_id, vectors)
        if lines:
            finish(db, job_id, "rejected", as_problems(lines))
            conn.commit()
            store.delete(keys)
            logger.info(f"Enrolment job {job_id} for {person_id} rejected: {len(lines)} problem(s); photos deleted")
            return True

        folder = Path(dataset) / person_id
        folder.mkdir(parents=True, exist_ok=True)
        save(folder, person_id, vectors.values())
        db.execute("SELECT pg_advisory_lock(%s)", (PUBLISH_LOCK,))
        try:
            publish(dataset)
        finally:
            db.execute("SELECT pg_advisory_unlock(%s)", (PUBLISH_LOCK,))
        old = store.list(f"persons/{person_id}/")
        for pose, data in photos.items():
            store.put(f"persons/{person_id}/{pose}.jpg", data)
        store.delete([key for key in old if key.rsplit("/", 1)[-1][:-4] not in photos] + keys)
        db.execute("UPDATE persons SET enrolled_at = now() WHERE person_id = %s", (person_id,))
        finish(db, job_id, "accepted")
    logger.info(f"Enrolment job {job_id} for {person_id} accepted: {len(vectors)} vectors published")
    return True


def main():
    store = Store()
    client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)

    def collection():
        create_connection(host=MILVUS_HOST, port=MILVUS_PORT)
        live = create_collection(MILVUS_COLLECTION_NAME)
        live.load()
        return live

    def forget_vectors(person_id):  # it rebuilds the collection like publish, so it waits for any publish in progress
        with conn.cursor() as db:
            db.execute("SELECT pg_advisory_lock(%s)", (PUBLISH_LOCK,))
            try:
                forget(person_id)
            finally:
                db.execute("SELECT pg_advisory_unlock(%s)", (PUBLISH_LOCK,))

    conn, frames_checked = None, -FRAME_CHECK_SECONDS
    while True:
        try:
            conn = conn if conn and not conn.closed else connect()
            expire(conn, store)
            deleted = enrolment_deletion.run_one(conn, store, forget_vectors)
            if time.monotonic() - frames_checked >= FRAME_CHECK_SECONDS:
                enrolment_deletion.clear_frames(conn)
                frames_checked = time.monotonic()
            if not process(conn, store, client, collection) and not deleted:
                time.sleep(IDLE_SECONDS)
        except Exception as error:  # a failed job stays pending and is retried; it expires after the time limit
            logger.error(f"Enrolment worker: {error}", exc_info=True)
            if conn:
                conn.close()
            conn = None
            time.sleep(10)


if __name__ == "__main__":
    main()
