#!/usr/bin/env python3
"""
milvus_incremental_updater.py

Runs daily at 12:00 AM. Reads database table face_images for unprocessed images,
loads them from image_path, generates embeddings, updates local pickle,
inserts into Milvus, and marks DB records as processed.
"""

import os
import sys
import time
import pickle
import base64
import fcntl
import schedule
import psycopg2
import psycopg2.extras
import cv2
import numpy as np
from psycopg2 import sql
from psycopg2.extras import RealDictRow
from typing_extensions import List, Tuple
from pymilvus import connections, utility, Collection


# Local project imports
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(PARENT_DIR)

from parameters import (
    DYNAMIC_DATASET_EMBEDDINGS_PATH,
    MILVUS_STAGING_COLLECTION_NAME,
    INSIGHTFACE_HOST,
    INSIGHTFACE_PORT,
    MILVUS_HOST,
    MILVUS_PORT,
    POSTGRESQL_DATABASE_NAME,
    POSTGRESQL_HOST,
    POSTGRESQL_PORT
)
from insightface_face_detection import IFRClient
from milvus_server import (
    create_connection,
    create_collection,
)
from custom_logging import dynamic_face_data_collector_logger as logger


# Read credentials from the environment.
POSTGRESQL_USERNAME = os.environ.get("POSTGRES_USER")
POSTGRESQL_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# == Database Configuration ==
# # Main database configuration.
DB_CONFIG = {
    'dbname': POSTGRESQL_DATABASE_NAME,
    'user': POSTGRESQL_USERNAME,
    'password': POSTGRESQL_PASSWORD,
    'host': POSTGRESQL_HOST,
    'port': POSTGRESQL_PORT
}


# == Initialize InsightFace client ==
insightface_client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)
create_connection(host=MILVUS_HOST, port=MILVUS_PORT)
# Creates the collection on a fresh install; opening it directly crash-looped until another service created it
collection = create_collection(MILVUS_STAGING_COLLECTION_NAME)


# ----------------------------------------------------------------------------
# Pickle Helpers
# ----------------------------------------------------------------------------

def load_embeddings_pickle(path: str) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"names": [], "encodings": []}
    try:
        with open(path, "rb+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data = pickle.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        logger.warning("Could not load or parse pickle at %s, starting fresh", path)
    return data


def save_embeddings_pickle(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        pickle.dump(data, f)
        fcntl.flock(f, fcntl.LOCK_UN)
    logger.info("Saved embeddings pickle (%d vectors)", len(data["names"]))


def patch_embeddings_pickle(person_id: str, new_names: List[str], new_encs: List[np.ndarray]) -> None:
    pkl_path = os.path.join(DYNAMIC_DATASET_EMBEDDINGS_PATH, "dynamic-dataset.pkl")
    data = load_embeddings_pickle(pkl_path)

    # Filter out old entries
    filtered = [
        (n, e) for n, e in zip(data["names"], data["encodings"])
        if n != person_id
    ]
    names_clean, encs_clean = zip(*filtered) if filtered else ([], [])
    data["names"] = list(names_clean) + new_names
    data["encodings"] = list(encs_clean) + new_encs

    save_embeddings_pickle(pkl_path, data)


# ----------------------------------------------------------------------------
# Milvus Upsert
# ----------------------------------------------------------------------------

def upsert_person_to_milvus(person_id: str, names: List[str], encodings: List[np.ndarray]) -> None:
    if not names:
        logger.info("No new embeddings for %s, skipping", person_id)
        return

    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)

    if not utility.has_collection(MILVUS_STAGING_COLLECTION_NAME):
        create_collection(collection_name=MILVUS_STAGING_COLLECTION_NAME)
        logger.info("Created Milvus collection '%s'", MILVUS_STAGING_COLLECTION_NAME)

    collection = Collection(MILVUS_STAGING_COLLECTION_NAME)

    expr = f"name_id == '{person_id}'"
    try:
        collection.delete(expr=expr)
        collection.flush()
    except Exception as e:
        logger.error("Error deleting old vectors for %s: %s", person_id, e, exc_info=True)

    try:
        collection.insert([names, encodings])
        collection.flush()
        logger.info("Inserted %d new vectors for %s", len(names), person_id)
    except Exception as e:
        logger.error("Error inserting new vectors for %s: %s", person_id, e, exc_info=True)


# ----------------------------------------------------------------------------
# Main Batch Job: Process Unprocessed Images from DB
# ----------------------------------------------------------------------------
def is_processed(rows: List[RealDictRow]) -> bool:
    return all(row["is_processed"] for row in rows)


def upsert_person_summary(person_id, cursor):
    try:
        sql_query = sql.SQL("""
            SELECT * FROM face_images WHERE person_id = %s;
        """)
        cursor.execute(sql_query, (person_id,))
        rows = cursor.fetchall()
        processed = is_processed(rows)

        update_query = sql.SQL("""
            UPDATE person_summary
            SET is_processed = %s
            WHERE person_id = %s;
        """)
        cursor.execute(update_query, (processed, person_id))
    except Exception as error:
        logger.error(f"Error while updating person summary due to: {error}")


def process_unprocessed_images_from_db():
    logger.info("Starting overnight batch: Processing unprocessed images from DB")

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT id, person_id, image_path
                    FROM face_images
                    WHERE NOT is_processed
                """)
                rows = cursor.fetchall()

                if not rows:
                    logger.info("No unprocessed images found. Nothing to do.")
                    return

                person_images = {}
                for row in rows:
                    person_id = row["person_id"]
                    if person_id not in person_images:
                        person_images[person_id] = []
                    person_images[person_id].append((row["id"], row["image_path"]))

                for person_id, items in person_images.items():
                    logger.info("Processing person_id=%s with %d images", person_id, len(items))
                    names = []
                    encodings = []
                    processed_ids = []

                    for img_id, img_path in items:
                        try:
                            if not os.path.isabs(img_path):
                                img_path = os.path.abspath(img_path)
                            if not os.path.exists(img_path):
                                logger.warning("File does not exist: %s", img_path)
                                continue

                            img = cv2.imread(img_path)
                            if img is None:
                                logger.warning("Could not read image at path=%s", img_path)
                                continue

                            _, buf = cv2.imencode(".jpg", img)
                            b64_data = base64.b64encode(buf.tobytes()).decode("ascii")

                            result = insightface_client.extract(
                                data=[b64_data], extract_embedding=True
                            )
                            faces = result["data"][0]["faces"]
                            for face in faces:
                                vec = np.array(face["vec"], dtype=np.float32)
                                names.append(person_id)
                                encodings.append(vec)
                                processed_ids.append(img_id)
                        except Exception as ex:
                            logger.error("Error processing image id=%s: %s", img_id, ex, exc_info=True)

                    if not encodings:
                        logger.warning("No embeddings extracted for person_id=%s", person_id)
                        continue

                    # 1. Patch local pickle
                    patch_embeddings_pickle(person_id, names, encodings)

                    # 2. Upsert to Milvus
                    upsert_person_to_milvus(person_id, names, encodings)

                    # 3. Mark DB rows as processed
                    if processed_ids:
                        logger.info("Updating is_processed for IDs: %s", processed_ids)
                        cursor.execute("""
                            UPDATE face_images
                            SET is_processed = true
                            WHERE id IN %s
                            RETURNING id
                        """, (tuple(processed_ids),))
                        updated = cursor.fetchall()
                        conn.commit()
                        logger.info("Confirmed updated IDs in DB: %s", [row['id'] for row in updated])
                    else:
                        logger.warning("No processed IDs to update for person_id=%s", person_id)

                    upsert_person_summary(person_id, cursor)
                    conn.commit()

            conn.commit()
            logger.info("PostgreSQL transaction committed")

    except Exception as e:
        logger.error("Error in overnight batch job: %s", e, exc_info=True)

    time.sleep(15 * 60)
    logger.info(f"Total size of Milvus Collection {collection.name} is {collection.num_entities}")


# ----------------------------------------------------------------------------
# Main Scheduler
# ----------------------------------------------------------------------------

def main():
    logger.info("Starting Milvus Incremental Updater with daily schedule at 01:00 AM")

    # Ensure Milvus collection exists
    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)
    if not utility.has_collection(MILVUS_STAGING_COLLECTION_NAME):
        create_collection(collection_name=MILVUS_STAGING_COLLECTION_NAME)
        logger.info("Initialized Milvus collection '%s' with index", MILVUS_STAGING_COLLECTION_NAME)

    # Schedule daily at 00:00
    schedule.every().day.at("01:00").do(process_unprocessed_images_from_db)

    logger.info("Scheduler is now running. Waiting for jobs...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Shutting down scheduler gracefully")


if __name__ == "__main__":
    main()
