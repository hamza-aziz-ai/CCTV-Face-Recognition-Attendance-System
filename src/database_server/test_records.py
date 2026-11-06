"""Recognition records on a real PostgreSQL: they save, a repeat within the window is skipped, parallel batches of one person save once,
a batch saves whole or not at all within its deadline, a batch sent again unchanged saves nothing twice, a record arriving after its
person's pictures were cleared keeps none, the clearing and the inserts never deadlock, and the controller answers only after saving.
CI runs this against a throwaway PostgreSQL, with IP_ADDRESS, POSTGRES_USER, POSTGRES_PASSWORD, CLIENT_ID=owner and LEGACY_SHARED_SERVICES=1 set."""
import base64
import os
import sys
import threading
from contextlib import closing
from unittest import mock

import cv2
import numpy as np
import psycopg2
import psycopg2.extras

import postgresql_database as db

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "util"))

DAY = "2026-11-01"
_, JPEG = cv2.imencode(".jpg", np.zeros((64, 64, 3), np.uint8))
RECORD = ("maingate_entry_cctv-camera-1", "10.0.0.1", 0.9, base64.b64encode(JPEG).decode(), [5, 5, 30, 30])


def rows(person):
    with psycopg2.connect(**db.DB_CONFIG) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM recognition_results WHERE person_id = %s", (person,))
        return cursor.fetchone()[0]


def save(person, time, day=DAY):
    return db.insert_recognition_data(day, time, {person: [RECORD]})


def sql(query, args=()):
    with closing(psycopg2.connect(**db.DB_CONFIG)) as conn, conn, conn.cursor() as cursor:
        cursor.execute(query, args)
        return cursor.fetchall() if cursor.description else None


def refused(call, error):
    try:
        call()
    except error:
        return True
    raise AssertionError(f"expected {error.__name__}")


def test():
    db.initialize_database_and_partitions(None)

    save("alone", "10:00:00")
    assert rows("alone") == 1, "a record must save"
    save("alone", "10:04:00")
    assert rows("alone") == 1, "a repeat within the window must be skipped"
    save("alone", "10:06:00")
    assert rows("alone") == 2, "a record after the window must save"

    db.insert_recognition_data(DAY, "10:00:00", {"named": [("maingate_entry_cctv-camera-2", "http://localhost:8080/video", 0.9, RECORD[3], RECORD[4])]})
    assert rows("named") == 1, "a camera set by host name must save"
    db.insert_recognition_data(DAY, "10:00:00", {"gone": [("maingate_entry_cctv-camera-3", "no-such-camera.invalid", 0.9, RECORD[3], RECORD[4])]})
    assert rows("gone") == 1, "a camera that no longer resolves must keep its record"

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

    # A batch sent again unchanged, as after a lost answer, saves nothing twice however late; the window is the records' own time
    assert save("retry", "12:00:00") == (1, 0) and save("retry", "12:00:00") == (0, 1) and rows("retry") == 1
    # The window reaches across midnight
    assert save("midnight", "23:58:00", "2026-11-01") == (1, 0) and save("midnight", "00:02:00", "2026-11-02") == (0, 1)

    # A payload that can never be saved is refused before any database work
    refused(lambda: db.insert_recognition_data("2026-13-01", "10:00:00", {"bad": [RECORD]}), ValueError)
    refused(lambda: db.insert_recognition_data(DAY, "10:00:00", {}), ValueError)
    refused(lambda: db.insert_recognition_data(DAY, "10:00:00", {"bad": [RECORD[:4]]}), ValueError)
    refused(lambda: db.insert_recognition_data(DAY, "10:00:00", {"bad": [RECORD[:3] + ("not a picture", RECORD[4])]}), ValueError)

    # All or nothing: the second person's ID is too long for its column, so the first person's record is not kept either
    refused(lambda: db.insert_recognition_data(DAY, "13:00:00", {"first": [RECORD], "x" * 60: [RECORD]}), psycopg2.Error)
    assert rows("first") == 0, "a failed batch must leave nothing behind"
    real = db.ensure_year_location_partition_exists

    def broken_partition(cursor, location, year):
        raise psycopg2.OperationalError("no partition")

    with mock.patch.object(db, "ensure_year_location_partition_exists", broken_partition):
        refused(lambda: save("partition", "13:00:00"), psycopg2.Error)
    assert rows("partition") == 0

    # The deadline covers the whole batch, not one statement: three steps of 0.6 s each overrun 1 s
    def slow_partition(cursor, location, year):
        cursor.execute("SELECT pg_sleep(0.6)")
        real(cursor, location, year)

    cameras = [(f"site{i}_entry_cctv-camera-1",) + RECORD[1:] for i in range(3)]
    with mock.patch.object(db, "TRANSACTION_TIMEOUT", "1s"), mock.patch.object(db, "ensure_year_location_partition_exists", slow_partition):
        refused(lambda: db.insert_recognition_data(DAY, "14:00:00", {"slow": cameras}), psycopg2.Error)
    assert rows("slow") == 0

    # A record arriving after its person's pictures were cleared keeps no picture; one made after the request keeps it
    sql("""CREATE TABLE IF NOT EXISTS deletions (id UUID PRIMARY KEY, person_id TEXT NOT NULL, reason TEXT NOT NULL,
           requested_by TEXT NOT NULL, requested_at TIMESTAMPTZ NOT NULL DEFAULT now(), done_at TIMESTAMPTZ, frames_cleared_at TIMESTAMPTZ)""")
    sql("""INSERT INTO deletions VALUES ('00000000-0000-0000-0000-000000000001', 'cleared', 'left', 'test', '2026-11-01 12:00+00', now(), now())""")
    save("cleared", "09:00:00")
    save("cleared", "10:00:00", "2026-11-03")
    frames = sql("SELECT recognition_date, recognition_frame IS NULL FROM recognition_results WHERE person_id = 'cleared' ORDER BY 1")
    assert [cleared for _, cleared in frames] == [True, False], frames

    # The hourly clearing and batches of the same people take the same locks in the same order: no deadlock, and every
    # record of a person whose pictures are due ends up without one
    import enrolment_deletion

    people = [f"race{i}" for i in range(4)]
    for number, person in enumerate(people, start=2):
        sql("INSERT INTO deletions VALUES (%s, %s, 'left', 'test', now() - interval '4 years', now(), NULL)",
            (f"00000000-0000-0000-0000-00000000000{number}", person))
    errors = []

    def ingest(minute, year):
        try:
            records = {person: [(f"site{minute}_entry_cctv-camera-1",) + RECORD[1:]] for person in reversed(people)}
            db.insert_recognition_data(f"{year}-01-01", f"10:{minute:02d}:00", records)
        except Exception as error:
            errors.append(error)

    def clear():
        try:
            with closing(psycopg2.connect(**db.DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)) as conn:
                enrolment_deletion.clear_frames(conn)
        except Exception as error:
            errors.append(error)

    # Repeated, each round on a new year so every batch also creates partitions: the deadlock CI caught once on arm64
    # needed a batch creating a partition while another held a person lock
    for year in range(2010, 2020):
        racers = [threading.Thread(target=ingest, args=(minute, year)) for minute in range(0, 60, 10)] + [threading.Thread(target=clear)]
        for racer in racers:
            racer.start()
        for racer in racers:
            racer.join()
        assert not errors, errors
        sql("UPDATE deletions SET frames_cleared_at = NULL WHERE person_id LIKE 'race%%'")
    left = sql("SELECT count(*) FROM recognition_results WHERE person_id LIKE 'race%%' AND recognition_frame IS NOT NULL")[0][0]
    assert left == 0, f"{left} records kept a picture that was due to be cleared"

    # Lock order, deterministically: a transaction holds a person's lock and then writes; a batch for that person that also
    # creates a new partition must wait for it, not take the table first (CI hit that deadlock once on arm64)
    import time
    waiting = []
    with closing(psycopg2.connect(**db.DB_CONFIG)) as holder, holder.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('lockorder'))")
        batch = threading.Thread(target=lambda: waiting.append(save("lockorder", "10:00:00", "2005-01-01")))
        batch.start()
        time.sleep(1.5)  # the batch is now waiting for the person lock (it used to hold the new partition's table lock)
        cursor.execute("""INSERT INTO recognition_results (person_id, location, camera_name, camera_ip, recognition_date,
                          recognition_time, confidence_score) VALUES ('holder', 'maingate', 'maingate_entry_cctv-camera-1',
                          '10.0.0.1', %s, '10:00:00', 0.9)""", (DAY,))
        holder.commit()
    batch.join(30)
    assert waiting == [(1, 0)], f"the batch must save once the lock is free, got {waiting}"

    # The controller answers only once the batch is saved, says so, and refuses a bad payload with 400
    # (The endpoint is called directly: starlette's TestClient needs a package the image does not have)
    from fastapi import HTTPException
    import postgresql_server_controller as controller

    def status(body):
        try:
            return 200, controller.ingest_data(controller.RecognitionPayload(**body))
        except HTTPException as error:
            return error.status_code, None

    body = {"current_date": DAY, "current_time": "15:00:00", "results": {"api": [list(RECORD)]}}
    assert status(body) == (200, {"status": "OK", "committed": True, "inserted": 1, "deduplicated": 0}), status(body)
    assert rows("api") == 1
    assert status(dict(body, current_date="2026-13-01"))[0] == 400
    with mock.patch.object(controller, "insert_recognition_data", side_effect=psycopg2.OperationalError("down")):
        assert status(body)[0] == 503

    # Health: ready only while the latest write succeeded recently and none is overrunning
    db.write_health()
    assert sql("SELECT count(*) FROM service_health")[0][0] == 1
    controller.health.update(started=None, saved_at=100.0, failed=False)
    assert controller.database_writable(150.0) and not controller.database_writable(191.0)
    controller.health.update(started=145.0)
    assert not controller.database_writable(156.0), "a write running past its deadline must count as failing"
    controller.health.update(started=None, failed=True)
    assert not controller.database_writable(101.0)
    print("records ok (saved, repeat skipped, saved after the window, host names saved, 8 parallel batches saved once, "
          "unchanged retries and midnight deduplicated, bad payloads refused, failed batches leave nothing, whole-batch deadline, "
          "cleared pictures stay cleared without deadlock, answered only after saving, health)")


if __name__ == "__main__":
    test()
