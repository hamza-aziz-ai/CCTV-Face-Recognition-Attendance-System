"""Recognition records on a real PostgreSQL: they save, a repeat within the window is skipped, and parallel batches of one person save once.
CI runs this against a throwaway PostgreSQL, with IP_ADDRESS, POSTGRES_USER, POSTGRES_PASSWORD, CLIENT_ID=owner and LEGACY_SHARED_SERVICES=1 set."""
import base64
import threading

import cv2
import numpy as np
import psycopg2

import postgresql_database as db

DAY = "2026-11-01"
_, JPEG = cv2.imencode(".jpg", np.zeros((64, 64, 3), np.uint8))
RECORD = ("maingate_entry_cctv-camera-1", "10.0.0.1", 0.9, base64.b64encode(JPEG).decode(), [5, 5, 30, 30])


def rows(person):
    with psycopg2.connect(**db.DB_CONFIG) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM recognition_results WHERE person_id = %s", (person,))
        return cursor.fetchone()[0]


def save(person, time):
    db.insert_recognition_data(DAY, time, {person: [RECORD]})


def test():
    db.initialize_database_and_partitions(None)

    save("alone", "10:00:00")
    assert rows("alone") == 1, "a record must save"
    save("alone", "10:04:00")
    assert rows("alone") == 1, "a repeat within the window must be skipped"
    save("alone", "10:06:00")
    assert rows("alone") == 2, "a record after the window must save"

    start = threading.Barrier(8)

    def parallel():
        start.wait()
        save("parallel", "11:00:00")

    threads = [threading.Thread(target=parallel) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert rows("parallel") == 1, f"parallel batches saved {rows('parallel')} rows, not 1"
    print("records ok (saved, repeat skipped, saved after the window, 8 parallel batches saved once)")


if __name__ == "__main__":
    test()
