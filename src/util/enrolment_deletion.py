"""Deleting a person's enrolment (8e), as notice 1.2 promises (owner, 2026-11-03).

Within ENROLMENT_DELETION_DAYS of withdrawing or leaving, everything about the person's face goes: their enrolment photos
in the bucket, their vectors, Milvus (a new version without them, and every older version, which may hold them), the
nightly update's crops, staging vectors and collector rows, their display portrait, their roster row, consents and jobs.
Their attendance records stay, and the camera pictures on them are cleared ENROLMENT_FRAME_YEARS after the request.

The API records the request in `deletions`; the enrolment worker runs it as soon as it sees it, and clears frames hourly.
Every step can run again, so a request that fails part-way stays open and is retried whole. The database rows go last.
"""
import fcntl
import os
import pickle
import shutil
import sys
from pathlib import Path

current = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [os.path.dirname(current), current]
from custom_logging import api_logger as logger  # noqa: E402
from parameters import DISPLAY_FACE_IMAGE_PATH, DYNAMIC_DATASET_EMBEDDINGS_PATH, DYNAMIC_DATASET_PATH, ENROLMENT_FRAME_YEARS, \
    FACIAL_RECOGNITION_DATASET_PATH  # noqa: E402

FOLDERS = (FACIAL_RECOGNITION_DATASET_PATH, DYNAMIC_DATASET_PATH, DISPLAY_FACE_IMAGE_PATH)
PICKLE = os.path.join(DYNAMIC_DATASET_EMBEDDINGS_PATH, "dynamic-dataset.pkl")


def remove_folder(root, person_id):
    """Only a folder directly inside root: an ID like ".." must never reach rmtree."""
    base = Path(root).resolve()
    target = (base / person_id).resolve()
    if target.parent != base:
        raise ValueError(f"refusing to delete {target}: not a person's folder in {base}")
    shutil.rmtree(target, ignore_errors=True)


def drop_from_pickle(path, person_id):
    """The nightly update's vectors, {"names": [...], "encodings": [...]}, under the same lock milvus_updater takes."""
    if not os.path.isfile(path):
        return
    with open(path, "r+b") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        data = pickle.load(file)  # our own file, written by milvus_updater
        keep = [(name, vector) for name, vector in zip(data["names"], data["encodings"]) if name != person_id]
        if len(keep) != len(data["names"]):
            data["names"], data["encodings"] = [name for name, _ in keep], [vector for _, vector in keep]
            file.seek(0)
            file.truncate()
            pickle.dump(data, file)


def forget_collected(person_id):
    """The nightly collector's rows in its own database: crops as bytes, and the per-person summary."""
    import psycopg2
    from parameters import POSTGRESQL_DATABASE_NAME, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login
    user, password = postgres_login()
    try:
        conn = psycopg2.connect(dbname=POSTGRESQL_DATABASE_NAME, user=user, password=password, host=POSTGRESQL_HOST,
                                port=POSTGRESQL_PORT, connect_timeout=5)
    except psycopg2.OperationalError as error:
        if "does not exist" in str(error):  # the collector has never run here
            return
        raise
    try:
        with conn, conn.cursor() as db:
            db.execute("SELECT to_regclass('face_images') IS NOT NULL, to_regclass('person_summary') IS NOT NULL")
            images, summary = db.fetchone()
            if images:
                db.execute("DELETE FROM face_images WHERE person_id = %s", (person_id,))
            if summary:
                db.execute("DELETE FROM person_summary WHERE person_id = %s", (person_id,))
    finally:
        conn.close()


def run_one(conn, store, forget_vectors, forget_rows=forget_collected, folders=FOLDERS, pickle_path=PICKLE) -> bool:
    """Runs the oldest open deletion. Returns whether there was one. forget_vectors(person_id) clears Milvus."""
    with conn, conn.cursor() as db:
        db.execute("SELECT id, person_id FROM deletions WHERE done_at IS NULL ORDER BY requested_at LIMIT 1 FOR UPDATE SKIP LOCKED")
        request = db.fetchone()
        if not request:
            return False
        person_id = request["person_id"]
        db.execute("SELECT id FROM enrolment_jobs WHERE person_id = %s", (person_id,))
        prefixes = [f"persons/{person_id}/"] + [f"jobs/{row['id']}/" for row in db.fetchall()]
        store.delete([key for prefix in prefixes for key in store.list(prefix)])
        for folder in folders:
            remove_folder(folder, person_id)
        drop_from_pickle(pickle_path, person_id)
        forget_rows(person_id)
        forget_vectors(person_id)
        for table in ("enrolment_jobs", "consents", "persons"):
            db.execute(f"DELETE FROM {table} WHERE person_id = %s", (person_id,))
        db.execute("UPDATE deletions SET done_at = now() WHERE id = %s", (request["id"],))
    logger.info(f"Deletion {request['id']} done: {person_id}'s face data is gone; attendance records kept")
    return True


def clear_frames(conn) -> int:
    """Clears the camera pictures on attendance records ENROLMENT_FRAME_YEARS after a deletion was requested. Records
    made after the request (the same ID registered again) keep theirs. Returns how many requests were cleared."""
    with conn, conn.cursor() as db:
        db.execute("""SELECT id, person_id, requested_at FROM deletions WHERE done_at IS NOT NULL AND frames_cleared_at IS NULL
                      AND requested_at < now() - make_interval(years => %s) FOR UPDATE SKIP LOCKED""", (ENROLMENT_FRAME_YEARS,))
        due = db.fetchall()
        db.execute("SELECT to_regclass('recognition_results') IS NOT NULL AS present")
        records = db.fetchone()["present"]
        for request in due:
            if records:
                db.execute("""UPDATE recognition_results SET recognition_frame = NULL WHERE person_id = %s
                              AND recognition_date <= %s::date AND recognition_frame IS NOT NULL""", (request["person_id"], request["requested_at"]))
            db.execute("UPDATE deletions SET frames_cleared_at = now() WHERE id = %s", (request["id"],))
    for request in due:
        logger.info(f"Deletion {request['id']}: camera pictures on {request['person_id']}'s attendance records cleared")
    return len(due)
