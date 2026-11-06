import os
import socket
import sys
from contextlib import closing
from typing import Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import numpy as np
import cv2
import base64
from datetime import datetime, timedelta
from urllib.parse import urlparse

# Ensure the parent directory is on the path for module imports.
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import (
    LEGACY_SHARED_SERVICES,
    postgres_login,
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
    POSTGRESQL_DATABASE,
    SAME_CAM_TIME_ENTRY_THRESHOLD,
    CAMERA_CONFIGURATION_FILE,
)
from custom_logging import database_server_logger

# Read credentials from the environment.
POSTGRESQL_USERNAME, POSTGRESQL_PASSWORD = postgres_login()  # this client's own role (D-037)

# Main database configuration.
DB_CONFIG = {
    'dbname': POSTGRESQL_DATABASE,
    'user': POSTGRESQL_USERNAME,
    'password': POSTGRESQL_PASSWORD,
    'host': POSTGRESQL_HOST,
    'port': POSTGRESQL_PORT
}


def ensure_database_exists():
    """
    Ensure that the main database exists.
    If not, connect to the default database and create it.
    """
    if not LEGACY_SHARED_SERVICES:
        return  # deploy/provision.py made it, owned by this client's role, which cannot create databases (D-037)
    try:
        default_config = DB_CONFIG.copy()
        default_config['dbname'] = 'postgres'
        # Establish connection
        conn = psycopg2.connect(**default_config)
        # Set autocommit to ensure commands run outside a transaction
        conn.autocommit = True

        with conn.cursor() as cursor:
            # Check if the target database exists
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s;",
                (DB_CONFIG['dbname'],)
            )
            if not cursor.fetchone():
                database_server_logger.info(
                    f"Database '{DB_CONFIG['dbname']}' does not exist. Creating it..."
                )
                # Execute CREATE DATABASE outside of a transaction block
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(DB_CONFIG['dbname'])
                    )
                )
        conn.close()  # Explicitly close the connection
        database_server_logger.info(f"Database '{DB_CONFIG['dbname']}' is ready.")
    except Exception as error:
        database_server_logger.error(f"Error ensuring database exists: {error}")
        raise



def ensure_unified_table_exists(cursor):
    """
    Ensure that the unified base table for recognition results exists.
    This table is partitioned by RANGE on 'recognition_date'.
    """
    try:
        create_table_query = sql.SQL("""
            CREATE TABLE recognition_results (
                id SERIAL,
                person_id VARCHAR(50) NOT NULL,
                location VARCHAR(50) NOT NULL,
                camera_name VARCHAR(100) NOT NULL,
                camera_ip INET NOT NULL,
                recognition_date DATE NOT NULL,
                recognition_time TIME NOT NULL,
                confidence_score NUMERIC(9,6) NOT NULL,
                api_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
                recognition_frame BYTEA,
                PRIMARY KEY (id, recognition_date, location)
            ) PARTITION BY RANGE (recognition_date);
        """)
        cursor.execute(create_table_query)
        database_server_logger.info("Base table 'recognition_results' is ensured.")
    except psycopg2.errors.DuplicateTable as e:
        # If the table already exists, log at INFO and ignore.
        database_server_logger.info("Base table 'recognition_results' already exists. Skipping creation.")
    except Exception as error:
        database_server_logger.error(f"Error ensuring base table exists: {error}")
        raise


def ensure_year_location_partition_exists(cursor, location, current_year):
    """
    Ensure that the partition for the given year and location exists.
    First, ensure the parent partition for the year exists (partitioned by RANGE on recognition_date),
    then create the child partition for the specified location.
    """
    parent_partition = f"recognition_results_{current_year}"
    start_date = f"{current_year}-01-01"
    end_date = f"{current_year + 1}-01-01"
    child_partition = f"{parent_partition}_{location}"
    # CREATE TABLE IF NOT EXISTS is not safe against itself: two batches creating the same new partition at once make one
    # fail with DuplicateTable. A lock per partition, held to the commit, lets the second find the first's table
    for name in (parent_partition, child_partition):
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"partition:{name}",))
    try:
        create_parent_query = sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} 
            PARTITION OF recognition_results
            FOR VALUES FROM (%s) TO (%s)
            PARTITION BY LIST (location);
        """).format(sql.Identifier(parent_partition))
        cursor.execute(create_parent_query, (start_date, end_date))
        database_server_logger.info(f"Parent partition for year '{current_year}' is ensured.")
    except Exception as error:
        database_server_logger.error(
            f"Error ensuring parent partition for location '{current_year}': {error}"
        )
        raise

    # Define the child partition for the specific academic year.
    try:
        create_child_query = sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} 
            PARTITION OF {} 
            FOR VALUES IN (%s);
        """).format(sql.Identifier(child_partition), sql.Identifier(parent_partition))
        cursor.execute(create_child_query, (location,))
        database_server_logger.info(
            f"Location partition '{child_partition}' for year '{current_year}' is ensured."
        )
    except Exception as error:
        database_server_logger.error(
            f"Error ensuring location partition for year '{current_year}' and location '{location}': {error}"
        )
        raise


def initialize_database_and_partitions(camera_config):
    """
    Initialize the database and ensure that the unified base table exists.
    Partitions for each location and year will be created on demand during data insertion.
    """
    try:
        ensure_database_exists()
        with closing(psycopg2.connect(**DB_CONFIG)) as conn:
            with conn.cursor() as cursor:
                # Committed on its own: the recognition table's DuplicateTable below aborts its transaction
                cursor.execute("CREATE TABLE IF NOT EXISTS service_health (name TEXT PRIMARY KEY, checked_at TIMESTAMPTZ NOT NULL)")
                conn.commit()
                ensure_unified_table_exists(cursor)
            conn.commit()
        database_server_logger.info("Database and unified table initialized successfully.")
    except Exception as error:
        database_server_logger.error(f"Error during database initialization: {error}")
        raise



def plot_bbox(frame: np.ndarray, bbox: list, person_id: str, face_matching_score: float) -> Optional[bytes]:
    """
    Draw a bounding box and label on the provided frame.

    Returns:
        The JPEG-encoded frame as bytes, or None if encoding fails.
    """
    try:
        x_min, y_min, x_max, y_max = bbox
        # frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        color = (0, 255, 0)
        cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 2)
        cv2.putText(
            frame,
            f"{person_id} ({round(face_matching_score, 3)})",
            (x_min, max(y_min - 10, 0)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            2,
        )
        success, encoded_frame = cv2.imencode('.jpg', frame)
        if not success:
            raise ValueError("Failed to encode frame")
        return encoded_frame.tobytes()
    except Exception as e:
        database_server_logger.error(
            f"Exception while plotting bounding box for {person_id}: {e}"
        )
        return None


def base64_to_image(base64_frame: str) -> Optional[np.ndarray]:
    """
    Convert a base64 encoded frame to a NumPy array (image).

    Args:
        base64_frame (str): Base64 encoded string representing the image.

    Returns:
        np.ndarray: The decoded image as a NumPy array, or None if decoding fails.
    """
    try:
        frame_bytes = base64.b64decode(base64_frame)
        frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
        image = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        return image

    except Exception as e:
        print(f"Error decoding base64 frame: {e}")
        return None


def camera_address(address: str) -> str:
    """The IP address for the `camera_ip` inet column. A camera can be set by URL or host name; one that no longer resolves still keeps its record."""
    host = urlparse(address).hostname if address.startswith("http") else address
    try:
        return socket.gethostbyname(host)
    except OSError:
        return "0.0.0.0"


# The whole batch must finish well inside the sender's read timeout, so a slow database fails it rather than leaving the
# sender unsure whether it was saved
TRANSACTION_TIMEOUT = "20s"
LOCK_TIMEOUT = "10s"


def prepare_records(current_date: str, current_time: str, results: dict) -> tuple:
    """Checks a payload and turns it into rows before any database work: decoding frames and resolving camera addresses
    never hold a lock. Raises ValueError for a payload that can never be saved."""
    event = datetime.strptime(f"{current_date} {current_time}", "%Y-%m-%d %H:%M:%S")
    if not isinstance(results, dict) or not results:
        raise ValueError("no results")
    rows = []
    for person_id, records in sorted(results.items()):
        if not person_id or not isinstance(records, list):
            raise ValueError("a result needs a person ID and a list of records")
        for record in records:
            if not isinstance(record, (list, tuple)) or len(record) != 5:
                raise ValueError("a record needs camera name, camera address, score, frame and box")
            camera_name, camera_ip, confidence_score, frame_base64, bbox = record
            frame = base64_to_image(frame_base64)
            if frame is None:
                raise ValueError("a record's frame is not a readable image")
            rows.append((person_id, camera_name.split("_")[0], camera_name, camera_address(camera_ip), float(confidence_score),
                         plot_bbox(frame, bbox, person_id, confidence_score)))
    return event, rows


def insert_recognition_data(current_date: str, current_time: str, results: dict) -> tuple:
    """Saves one batch of recognition records in one transaction and returns (inserted, deduplicated) once it is
    committed. A record is skipped as a duplicate when the same person has one on the same camera within
    SAME_CAM_TIME_ENTRY_THRESHOLD minutes before it, by the records' own time, so a batch sent again unchanged, even much
    later, saves nothing twice. Raises ValueError for a bad payload and psycopg2.Error when the database fails; either way
    nothing of the batch is saved.

    Arguments:
        current_date (str): Date in 'YYYY-MM-DD' format.
        current_time (str): Time in 'HH:MM:SS' format.
        results (dict): A mapping of person_id to a list of
                        (camera_name, camera_ip, confidence_score, frame_base64, bbox).
    """
    event, rows = prepare_records(current_date, current_time, results)
    window_start = event - timedelta(minutes=SAME_CAM_TIME_ENTRY_THRESHOLD)
    inserted = deduplicated = 0
    options = f"-c transaction_timeout={TRANSACTION_TIMEOUT} -c lock_timeout={LOCK_TIMEOUT}"
    with closing(psycopg2.connect(**DB_CONFIG, options=options)) as conn, conn, conn.cursor() as cursor:
        for location in sorted({row[1] for row in rows}):
            ensure_year_location_partition_exists(cursor, location, event.year)
        cursor.execute("SELECT to_regclass('deletions') IS NOT NULL")
        has_deletions = cursor.fetchone()[0]
        # One lock per person, taken in order and held to the commit: parallel batches of one person save once, and the
        # hourly clearing of camera pictures (enrolment_deletion.clear_frames) takes the same locks in the same order
        for person_id in sorted({row[0] for row in rows}):
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (person_id,))
        for person_id, location, camera_name, camera_ip, confidence_score, recognition_frame in rows:
            cursor.execute("""SELECT 1 FROM recognition_results
                              WHERE person_id = %s AND location = %s AND camera_name = %s
                                AND recognition_date BETWEEN %s AND %s
                                AND recognition_date + recognition_time BETWEEN %s AND %s""",
                           (person_id, location, camera_name, window_start.date(), event.date(), window_start, event))
            if cursor.fetchone():
                deduplicated += 1
                continue
            if has_deletions and recognition_frame is not None:
                # A record arriving after its person's pictures were cleared (8e) keeps no picture either
                cursor.execute("""SELECT 1 FROM deletions WHERE person_id = %s AND frames_cleared_at IS NOT NULL
                                  AND %s::date <= requested_at::date LIMIT 1""", (person_id, event.date()))
                if cursor.fetchone():
                    recognition_frame = None
            cursor.execute("""INSERT INTO recognition_results
                              (person_id, location, camera_name, camera_ip, recognition_date, recognition_time, confidence_score, recognition_frame)
                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                           (person_id, location, camera_name, camera_ip, event.date(), event.time(), confidence_score, recognition_frame))
            inserted += 1
    database_server_logger.info(f"Batch of {current_date} {current_time}: {inserted} saved, {deduplicated} duplicates skipped")
    return inserted, deduplicated


def write_health():
    """Commits one row, proving this client's database accepts writes now."""
    with closing(psycopg2.connect(**DB_CONFIG, connect_timeout=5)) as conn, conn, conn.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', '5s', true)")
        cursor.execute("""INSERT INTO service_health (name, checked_at) VALUES ('database-controller', now())
                          ON CONFLICT (name) DO UPDATE SET checked_at = excluded.checked_at""")
