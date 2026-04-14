import os
import sys
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
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
    POSTGRESQL_DATABASE,
    SAME_CAM_TIME_ENTRY_THRESHOLD,
    CAMERA_CONFIGURATION_FILE,
)
from custom_logging import database_server_logger

# Read credentials from the environment.
POSTGRESQL_USERNAME = os.environ.get("POSTGRES_USER")
POSTGRESQL_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

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
    child_partition = f"{parent_partition}_{location}"
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
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
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


def insert_recognition_data(current_date: str, current_time: str, results: dict):
    """
    Insert recognition data into the PostgreSQL database while avoiding duplicate
    entries within the SAME_CAM_TIME_ENTRY_THRESHOLD (in minutes).

    Arguments:
        current_date (str): Date in 'YYYY-MM-DD' format.
        current_time (str): Time in 'HH:MM:SS' format.
        results (dict): A mapping of person_id to a list of tuples,
                        where each tuple contains:
                          (camera_name, camera_ip, confidence_score, frame_base64, bbox)
    """
    try:
        current_year = datetime.strptime(current_date, "%Y-%m-%d").year
    except Exception as e:
        database_server_logger.error(
            f"Invalid date format for current_date: {current_date}. Error: {e}"
        )
        return

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                # Now, for each record, ensure partition exists.
                for person_id, records in results.items():
                    for record in records:
                        camera_name, camera_ip, confidence_score, frame_base64, bbox = record
                        frame = base64_to_image(frame_base64)
                        if camera_ip.startswith("http"):
                            camera_ip = urlparse(camera_ip).hostname
                        recognition_frame = plot_bbox(frame, bbox, person_id, confidence_score)

                        # Determine location from camera_name (assuming the first part denotes location).
                        location = camera_name.split("_")[0]

                        # Calculate time threshold.
                        current_datetime = datetime.strptime(
                            f"{current_date} {current_time}", "%Y-%m-%d %H:%M:%S"
                        )
                        threshold_datetime = current_datetime - timedelta(
                            minutes=SAME_CAM_TIME_ENTRY_THRESHOLD
                        )
                        time_threshold = threshold_datetime.strftime("%H:%M:%S")

                        # Check for duplicate entries within the threshold.
                        select_query = sql.SQL("""
                            SELECT 1 FROM recognition_results
                            WHERE person_id = %s
                              AND location = %s
                              AND camera_name = %s
                              AND recognition_timestamp BETWEEN %s - INTERVAL '%s minutes' AND %s
                        """)
                        # ensure_year_location_partition_exists(cursor, location, current_year)
                        cursor.execute(
                            select_query,
                            (person_id, location, camera_name, current_datetime, SAME_CAM_TIME_ENTRY_THRESHOLD, current_datetime)
                        )
                        if cursor.fetchone():
                            database_server_logger.warning(
                                f"Skipping entry for {person_id} at camera {camera_name} "
                                f"(record exists within {SAME_CAM_TIME_ENTRY_THRESHOLD} minutes)."
                            )
                            continue

                        # Try ensuring partition
                        try:
                            ensure_year_location_partition_exists(cursor, location, current_year)
                        except Exception as ddl_error:
                            conn.rollback()  # rollback the aborted transaction before continuing
                            database_server_logger.error(f"Error ensuring partition for {location}: {ddl_error}")
                            # Optionally, decide whether to skip this record or re-open a new transaction
                            continue

                        # Insert the record into the unified table. PostgreSQL will route the data to the correct partition.
                        insert_query = sql.SQL("""
                            INSERT INTO recognition_results
                            (person_id, location, camera_name, camera_ip, recognition_date, recognition_time, confidence_score, recognition_frame)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                        """)
                        cursor.execute(
                            insert_query,
                            (person_id, location, camera_name, camera_ip, current_date, current_time, confidence_score, recognition_frame)
                        )
                        database_server_logger.info(
                            f"Inserted entry for {person_id} under {camera_name}."
                        )
            conn.commit()
    except Exception as error:
        database_server_logger.error(f"Error while inserting data: {error}")
