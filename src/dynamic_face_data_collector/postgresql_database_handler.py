import os
import sys
import json
from typing import Optional, List, Dict
from collections import Counter
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor, RealDictRow
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
    POSTGRESQL_DATABASE_NAME,
    NUMBER_OF_PICTURES
)
from custom_logging import dynamic_face_data_collector_logger

# Read credentials from the environment.
POSTGRESQL_USERNAME = os.environ.get("POSTGRES_USER")
POSTGRESQL_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# Main database configuration.
DB_CONFIG = {
    'dbname': POSTGRESQL_DATABASE_NAME,
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
                dynamic_face_data_collector_logger.info(
                    f"Database '{DB_CONFIG['dbname']}' does not exist. Creating it..."
                )
                # Execute CREATE DATABASE outside the transaction block
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(DB_CONFIG['dbname'])
                    )
                )
        conn.commit()
        conn.close()  # Explicitly close the connection
        dynamic_face_data_collector_logger.info(f"Database '{DB_CONFIG['dbname']}' is ready.")
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error ensuring database exists: {error}")
        raise


def ensure_person_summary_table_exists(cursor):
    """
    Ensure that the `person_summary` table exists otherwise create it.
    """
    try:
        create_table_query = sql.SQL("""
            CREATE TABLE IF NOT EXISTS person_summary (
                id SERIAL,
                person_id VARCHAR,
                number_of_images INTEGER,
                collection_timestamp TIMESTAMP,
                updation_timestamp TIMESTAMP,
                is_processed BOOLEAN DEFAULT FALSE,
                images_per_cluster JSONB,
                PRIMARY KEY (person_id)
            );
        """)
        cursor.execute(create_table_query)
        dynamic_face_data_collector_logger.info("Base table 'person_summary' is ensured.")
    except psycopg2.errors.DuplicateTable as e:
        # If the table already exists, log at INFO and ignore.
        dynamic_face_data_collector_logger.info("Base table 'person_summary' already exists. Skipping creation.")
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error ensuring base table exists: {error}")
        raise f"Error ensuring base table exists: {error}"


def ensure_face_images_table_exists(cursor):
    """
    Ensure that the `face_images` table exists otherwise create it.
    """
    try:
        create_table_query = sql.SQL("""
            CREATE TABLE IF NOT EXISTS face_images (
                id SERIAL,
                person_id VARCHAR,
                image_path TEXT,
                image BYTEA,
                camera_name VARCHAR,
                cluster_id VARCHAR,
                pupil_distance FLOAT,
                face_matching_score FLOAT,
                is_processed BOOLEAN DEFAULT FALSE,
                insertion_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, cluster_id, image_path),
                FOREIGN KEY (person_id) REFERENCES person_summary(person_id)
            );
        """)
        cursor.execute(create_table_query)
        dynamic_face_data_collector_logger.info("Base table 'face_images' is ensured.")
    except psycopg2.errors.DuplicateTable as e:
        # If the table already exists, log at INFO and ignore.
        dynamic_face_data_collector_logger.info("Base table 'faceImages' already exists. Skipping creation.")
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error ensuring base table exists: {error}")
        raise


def initialize_database_and_tables() -> None:
    """
    Initialize the database and create base tables.

    Raises:
        Exception: If initialization fails.
    """
    try:
        ensure_database_exists()
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                ensure_person_summary_table_exists(cursor)
                ensure_face_images_table_exists(cursor)
            conn.commit()
        dynamic_face_data_collector_logger.info("Database, unified tables, and partitions initialized successfully.")
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error during database initialization: {error}")
        raise


def ensure_person_summary_exists(cursor: psycopg2.extensions.cursor, person_id: str, collection_timestamp: datetime):
    select_query = sql.SQL("""
        SELECT 1 FROM person_summary
        WHERE person_id = %s;
    """)
    cursor.execute(select_query, (person_id,))
    if not cursor.fetchone():
        insert_placeholder = sql.SQL("""
            INSERT INTO person_summary
            (person_id, collection_timestamp)
            VALUES (%s, %s);
        """)
        try:
            cursor.execute(insert_placeholder, (person_id, collection_timestamp))
            dynamic_face_data_collector_logger.info(
                f"Inserted first entry {person_id} on {collection_timestamp}."
            )
        except Exception as error:
            dynamic_face_data_collector_logger.error(
                f"Error inserting entry for {person_id} for {collection_timestamp}: {error}"
            )


def insert_face_data(person_id: str, image_path: str, camera_name: str, cluster_id: str, pupil_distance: float, face_matching_score: float):
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                filename = image_path.split("/")[-1]
                basename = filename[:-4]
                timestamp: datetime = datetime.strptime(basename, "%Y%m%d_%H%M%S_%f")
                ensure_person_summary_exists(cursor, person_id, timestamp)
                # Open image to read data and save in SQL database
                with open(image_path, "rb") as image_file:
                    image_bytes = image_file.read()

                # Insert the record into the unified table. PostgreSQL will route the data to the correct partition.
                insert_query = sql.SQL("""
                    INSERT INTO face_images
                    (person_id, image_path, image, camera_name, cluster_id, pupil_distance, face_matching_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """)
                cursor.execute(
                    insert_query,
                    (person_id, image_path, image_bytes, camera_name, cluster_id, pupil_distance, face_matching_score)
                )
                dynamic_face_data_collector_logger.info(
                    f"Face dataset updated for {person_id} under (cluster-{cluster_id}: {camera_name})."
                )
                upsert_person_summary(person_id, cursor)
            conn.commit()
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error while inserting data: {error}")


def delete_face_data(person_id: str, worst_image_file_path: str, cluster_id: str):
    try:
        # Normalize the path to match DB storage
        if "DYNAMIC-FACIAL-RECOGNITION-DATASET" in worst_image_file_path:
            idx = worst_image_file_path.index("DYNAMIC-FACIAL-RECOGNITION-DATASET")
            relative_path = worst_image_file_path[idx:]
        else:
            relative_path = worst_image_file_path

        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Delete the worst image from the database.
                delete_query = sql.SQL("""
                    DELETE FROM face_images WHERE person_id = %s AND cluster_id = %s AND image_path = %s;
                """)
                cursor.execute(
                    delete_query,
                    (person_id, cluster_id, relative_path)
                )
                dynamic_face_data_collector_logger.warning(
                    f"Deleted worst face image with details: ({person_id}, {cluster_id}, {relative_path})"
                )
                upsert_person_summary(person_id, cursor)
            conn.commit()
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error while deleting data: {error}")


def get_latest_timestamp(rows: List[RealDictRow]) -> datetime:
    latest_timestamp = rows[0]["insertion_timestamp"]
    for row in rows:
        if row["insertion_timestamp"] > latest_timestamp:
            latest_timestamp = row["insertion_timestamp"]

    return latest_timestamp


def get_cluster_wise_number_of_images(rows: List[RealDictRow]) -> str:
    counts = Counter(row["cluster_id"] for row in rows)
    return json.dumps(counts)


def is_processed(rows: List[RealDictRow]) -> bool:
    return all(row["is_processed"] for row in rows)


def upsert_person_summary(person_id, cursor):
    try:
        sql_query = sql.SQL("""
            SELECT * FROM face_images WHERE person_id = %s;
        """)
        cursor.execute(sql_query, (person_id,))
        rows = cursor.fetchall()
        updation_timestamp = get_latest_timestamp(rows)
        cluster_image_map = get_cluster_wise_number_of_images(rows)
        processed = is_processed(rows)
        number_of_images = len(rows)

        update_query = sql.SQL("""
            UPDATE person_summary
            SET number_of_images = %s,
                updation_timestamp = %s,
                is_processed = %s,
                images_per_cluster = %s
            WHERE person_id = %s;
        """)
        cursor.execute(update_query, (number_of_images, updation_timestamp, processed, cluster_image_map, person_id))
    except Exception as error:
        dynamic_face_data_collector_logger.error(f"Error while updating person summary due to: {error}")
