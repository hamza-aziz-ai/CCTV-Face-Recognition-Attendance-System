#!/usr/bin/env python3
"""
Optimized FastAPI application leveraging composite partitioning
with a PostgreSQL connection pool and robust error handling.
"""

import os
import sys
import json
import io
from datetime import datetime
from contextlib import asynccontextmanager, contextmanager
from typing import Generator, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
import requests
from apscheduler.schedulers.background import BackgroundScheduler

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyQuery

from psycopg2 import pool, OperationalError
from psycopg2.extras import RealDictCursor

# Ensure the parent directory is on the path.
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from util.generic_utilities import map_camera_to_api_endpoint
from parameters import (
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
    POSTGRESQL_DATABASE,
    CAMERA_CONFIGURATION_FILE,
    METRIC_TYPE
)
from custom_logging import api_logger

# -------------------- Global Configuration & Globals --------------------

CAMERA_TO_API_MAP = map_camera_to_api_endpoint()

POSTGRESQL_USERNAME = os.environ.get("POSTGRESQL_USERNAME")
POSTGRESQL_PASSWORD = os.environ.get("POSTGRESQL_PASSWORD")
DB_CONFIG = {
    "dbname": POSTGRESQL_DATABASE,
    "user": POSTGRESQL_USERNAME,
    "password": POSTGRESQL_PASSWORD,
    "host": POSTGRESQL_HOST,
    "port": POSTGRESQL_PORT,
}

API_KEY = os.environ.get("API_KEY")
api_key_query = APIKeyQuery(name="api_key")

# Global connection pool; it will be initialized on startup.
db_pool: Optional[pool.ThreadedConnectionPool] = None

# -------------------- Database Connection Pool Context Manager --------------------

@contextmanager
def get_db_cursor(commit: bool = False, dict_cursor: bool = True) -> Generator:
    """
    Context manager to obtain a cursor from the connection pool.
    Commits changes if commit=True.
    """
    global db_pool
    if db_pool is None:
        raise RuntimeError("Database connection pool is not initialized.")
    conn = db_pool.getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor) if dict_cursor else conn.cursor()
        yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        api_logger.error(f"DB operation error: {e}")
        raise
    finally:
        cursor.close()
        db_pool.putconn(conn)

# -------------------- Helper Functions --------------------

def load_camera_configuration() -> list:
    """Load camera configuration and return a list of location names."""
    try:
        with open(CAMERA_CONFIGURATION_FILE, "r") as file:
            config = json.load(file)
        return list(config.keys())
    except Exception as e:
        api_logger.error(f"Error loading camera configuration: {e}")
        return []

def parse_date(date_str: str) -> Tuple[datetime, str]:
    """
    Parse the input date string (expected in 'DD-MM-YYYY').
    Returns a tuple: (datetime object, formatted date 'YYYY-MM-DD').
    """
    try:
        dt = datetime.strptime(date_str, "%d-%m-%Y")
    except ValueError:
        api_logger.warning("Invalid date format")
        raise HTTPException(status_code=400, detail="Invalid date format. Please use 'DD-MM-YYYY'.")
    if dt.date() > datetime.now().date():
        api_logger.warning("Future dates are not available.")
        raise HTTPException(
            status_code=400,
            detail="Future dates are not allowed. Please provide a past or present date."
        )
    return dt, dt.strftime("%Y-%m-%d")

def format_recognition_row(row: dict) -> dict:
    """Format a recognition row for API response."""
    try:
        rec_date = datetime.strptime(str(row["recognition_date"]), "%Y-%m-%d")
        rec_time = datetime.strptime(str(row["recognition_time"]), "%H:%M:%S")
        recognition_entry = {
            "person_id": row.get("person_id"),
            "location": row.get("location"),
            "camera_name": row.get("camera_name"),
            "camera_ip": row.get("camera_ip"),
            "recognition_date": rec_date.strftime("%d %B %Y, %A"),
            "recognition_time": rec_time.strftime("%I:%M:%S %p"),
        }
        if METRIC_TYPE == "COSINE":
            recognition_entry["cosine_similarity"] = float(row.get('confidence_score', 0))
        elif METRIC_TYPE == "L2":
            recognition_entry["euclidean_distance"] = float(row.get('confidence_score', 0))

        recognition_entry["api_acknowledged"] = row.get("api_acknowledged")

        return recognition_entry
    except Exception as e:
        api_logger.error(f"Error formatting row: {e}")
        return row

def decode_recognition_frame(row: dict) -> Tuple[Optional[np.ndarray], Optional[str]]:
    """
    Decode the recognition frame from the DB row into an image.
    Returns (image, metadata) or (None, None) on error.
    """
    recognition_frame = row.get("recognition_frame")
    recognition_time_str = str(row.get("recognition_time"))
    try:
        rec_time = datetime.strptime(recognition_time_str, "%H:%M:%S")
    except Exception:
        rec_time = None

    if recognition_frame is None:
        return None, None

    try:
        # Convert memoryview if needed.
        if isinstance(recognition_frame, memoryview):
            recognition_frame = recognition_frame.tobytes()
        image = plt.imread(io.BytesIO(recognition_frame), format="JPEG")
        meta = (
            f"Time: {rec_time.strftime('%I:%M:%S %p') if rec_time else ''} | "
            f"Camera: {row.get('camera_name')} ({row.get('camera_ip')})"
        )
        return image, meta
    except Exception as e:
        api_logger.error(f"Error decoding frame: {e}")
        return None, None

def update_api_acknowledged(row_id: int) -> None:
    """
    Update the 'api_acknowledged' flag to True for the given row.
    """
    query = """
        UPDATE recognition_results
        SET api_acknowledged = true
        WHERE id = %s;
    """
    try:
        with get_db_cursor(commit=True, dict_cursor=False) as cursor:
            cursor.execute(query, (row_id,))
    except Exception as e:
        api_logger.error(f"Error updating api_acknowledged for row {row_id}: {e}")

def fetch_unacknowledged_rows(current_date) -> list:
    """
    Retrieve all rows where api_acknowledged is false.
    """
    query = """
        SELECT id, person_id, camera_name, camera_ip, recognition_date, recognition_time, confidence_score, location
        FROM recognition_results
        WHERE api_acknowledged = false AND recognition_date = %s;
    """
    try:
        with get_db_cursor() as cursor:
            cursor.execute(query, (current_date,))
            rows = cursor.fetchall()
        return rows
    except Exception as e:
        api_logger.error(f"Error fetching unacknowledged rows: {e}")
        return []

def post_to_api(row: dict) -> None:
    """
    Post recognition data to the mapped API endpoint.
    On success, mark the row as acknowledged.
    """
    camera_name = row.get("camera_name")
    api_endpoint = CAMERA_TO_API_MAP.get(camera_name)
    if not api_endpoint:
        api_logger.info(f"No API endpoint mapped for camera: {camera_name}")
        return

    payload = {
        "entity": row.get("person_id"),
        "location": row.get("location"),
        "cam_name": row.get("camera_name"),
        "cam_ip": row.get("camera_ip"),
        "date": row.get("recognition_date").strftime("%d-%m-%Y")
        if hasattr(row.get("recognition_date"), "strftime") else row.get("recognition_date"),
        "time": row.get("recognition_time").strftime("%H:%M:%S")
        if hasattr(row.get("recognition_time"), "strftime") else row.get("recognition_time"),
        "similarity": float(row.get("confidence_score", 0)),
    }
    recognition_object = {"recognition": [payload]}

    try:
        response = requests.post(api_endpoint, json=recognition_object, timeout=60)
        if response.status_code == 200:
            resp_json = response.json()
            data = resp_json.get("data")

            if not data:
                api_logger.error(
                    f"API responded with null or empty 'data' for entry: {row.get('person_id')} | {row.get('camera_name')} | "
                    f"{payload['date']} | {payload['time']} | ErrorCode: {resp_json.get('errorcode')} | "
                    f"Message: {resp_json.get('errormessage')}"
                )
            else:
                status = data.get("status", "")
                if status.startswith("Status:") and status.endswith("Attendance Successfully Marked"):
                    api_logger.info(
                        f"Data posted successfully for entry: {row.get('person_id')} | {row.get('camera_name')} | "
                        f"{payload['date']} | {payload['time']} | Status: {status}"
                    )
                    update_api_acknowledged(row.get("id"))
                else:
                    api_logger.error(
                        f"Unexpected status for entry: {row.get('person_id')} | {row.get('camera_name')} | "
                        f"{payload['date']} | {payload['time']} | Status: {status}"
                    )
        else:
            api_logger.error(
                f"Failed to post data for entry: {row.get('person_id')} | {row.get('camera_name')} | "
                f"{payload['date']} | {payload['time']} - HTTP {response.status_code}: {response.reason}"
            )
    except Exception as e:
        api_logger.error(
            f"Exception occurred while posting data for entry: {row.get('person_id')} | {row.get('camera_name')} | "
            f"{payload['date']} | {payload['time']} - {e}"
        )


def process_unacknowledged_rows() -> None:
    """
    Process and post all unacknowledged rows.
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    rows = fetch_unacknowledged_rows(current_date)
    if not rows:
        api_logger.info("No unacknowledged rows found.")
        return

    api_logger.info(f"Found {len(rows)} unacknowledged rows. Processing...")
    for row in rows:
        post_to_api(row)

# -------------------- Scheduler --------------------

def start_scheduler() -> BackgroundScheduler:
    """
    Start a background scheduler to process unacknowledged rows.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(process_unacknowledged_rows, "interval", minutes=1)
    scheduler.start()
    api_logger.info("Scheduler started for processing unacknowledged rows.")
    return scheduler

# -------------------- FastAPI API Key Dependency --------------------

def get_api_key(api_key: str = Depends(api_key_query)) -> bool:
    if api_key == API_KEY:
        return True
    raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")

# -------------------- FastAPI Lifespan --------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    api_logger.info("Starting application...")

    # Initialize the DB connection pool
    try:
        db_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            **DB_CONFIG
        )
        api_logger.info("Database connection pool created.")
    except OperationalError as e:
        api_logger.error(f"Error creating DB connection pool: {e}")
        sys.exit(1)

    # Load camera configuration (can be cached globally if needed)
    load_camera_configuration()

    # Start background scheduler
    scheduler = start_scheduler()

    try:
        yield
    finally:
        # Shutdown scheduler and close all DB connections
        scheduler.shutdown()
        if db_pool:
            db_pool.closeall()
        api_logger.info("Shutting down application...")

app = FastAPI(lifespan=lifespan)

# -------------------- API Endpoints --------------------

@app.get("/fetch_tiled_frames")
def fetch_tiled_frames(date: str, person_id: str, api_key: bool = Depends(get_api_key)):
    """
    Fetch recognition frames for a given person and date,
    compose a tiled image, and return it as a PNG.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")
    try:
        dt, postgres_date = parse_date(date)
        year = dt.year
        # Use the subpartition table named with the year and module.
        table_name = f"recognition_results_{year}"
        # Query using both person_id and date; add location if known to benefit partition elimination.
        query = f"""
            SELECT camera_name, camera_ip, recognition_frame, recognition_time
            FROM {table_name}
            WHERE person_id = %s AND recognition_date = %s
            ORDER BY recognition_time;
        """
        with get_db_cursor() as cursor:
            cursor.execute(query, (person_id, postgres_date))
            results = cursor.fetchall()

        if not results:
            api_logger.warning("No data found for the specified date and person_id.")
            raise HTTPException(status_code=404, detail="No data found for the specified date and person_id.")

        frames, metadata = [], []
        for row in results:
            image, meta = decode_recognition_frame(row)
            if image is not None:
                frames.append(image)
                metadata.append(meta)

        if not frames:
            api_logger.warning("No valid frames found for the specified date and person_id.")
            raise HTTPException(status_code=404, detail="No valid frames found for the specified date and person_id.")

        # Calculate grid dimensions (maximum 2 columns).
        num_frames = len(frames)
        cols_count = 2 if num_frames >= 2 else 1
        rows_count = int(np.ceil(num_frames / cols_count))

        fig_width = cols_count * (640 / 100)
        fig_height = rows_count * (360 / 100)
        fig, axes = plt.subplots(rows_count, cols_count, figsize=(fig_width, fig_height))
        axes = axes.flatten() if (rows_count * cols_count) > 1 else [axes]

        for i, ax in enumerate(axes):
            if i < num_frames:
                ax.imshow(frames[i])
                ax.axis("off")
                ax.text(
                    0.5, -0.02, metadata[i],
                    transform=ax.transAxes, ha="center", va="top",
                    fontsize=10, color="black",
                    bbox=dict(facecolor="white", alpha=0.7, pad=2)
                )
            else:
                ax.axis("off")

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close(fig)
        return StreamingResponse(buf, media_type="image/png")

    except HTTPException as e:
        api_logger.error(f"HTTP Exception occurred: {e}")
        raise
    except Exception as e:
        api_logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.get("/fetch_person_data")
def fetch_person_data(date: str, person_id: str, camera_name: Optional[str] = None, api_key: bool = Depends(get_api_key)):
    """
    Fetch recognition results for a given person and date,
    and return formatted data.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")
    try:
        dt, postgres_date = parse_date(date)
        year = dt.year
        # Use the year partition table
        table_name = f"recognition_results_{year}"
        query = f"""
            SELECT person_id, camera_name, camera_ip, recognition_date, recognition_time,
                   confidence_score, api_acknowledged, location
            FROM {table_name}
            WHERE person_id = %s AND recognition_date = %s
        """
        params = [person_id, postgres_date]

        if camera_name:
            query += " AND camera_name = %s"
            params.append(camera_name)

        query += " ORDER BY recognition_time;"
        with get_db_cursor() as cursor:
            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

        if not results:
            return {"status": "success", "data": [], "message": "No records found for the specified date."}

        formatted_results = [format_recognition_row(row) for row in results]
        return {"status": "success", "data": formatted_results}

    except HTTPException as e:
        api_logger.warning(e)
        raise
    except Exception as e:
        api_logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


@app.get("/fetch_camera_data")
def fetch_camera_data(date: str, camera_name: str, api_key: bool = Depends(get_api_key)):
    """
    Fetch recognition results for a given person and date,
    and return formatted data.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")
    try:
        dt, postgres_date = parse_date(date)
        year = dt.year
        # Use the year partition table
        table_name = f"recognition_results_{year}"
        query = f"""
            SELECT person_id, camera_name, camera_ip, recognition_date, recognition_time,
                   confidence_score, api_acknowledged, location
            FROM {table_name}
            WHERE camera_name = %s AND recognition_date = %s
            ORDER BY recognition_time;
        """

        with get_db_cursor() as cursor:
            cursor.execute(query, (camera_name, postgres_date))
            results = cursor.fetchall()

        if not results:
            return {"status": "success", "data": [], "message": "No records found for the specified date."}

        formatted_results = [format_recognition_row(row) for row in results]
        return {"status": "success", "data": formatted_results}

    except HTTPException as e:
        api_logger.warning(e)
        raise
    except Exception as e:
        api_logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


@app.get("/fetch_module_data")
def fetch_module_data(date: str, module: str, api_key: bool = Depends(get_api_key)):
    """
    Fetch recognition results for a specific module (i.e. location) and date.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")
    try:
        dt, postgres_date = parse_date(date)
        year = dt.year
        # Use the subpartition table named with the year and module.
        table_name = f"recognition_results_{year}_{module}"
        query = f"""
            SELECT *
            FROM {table_name}
            WHERE location = %s AND recognition_date = %s
            ORDER BY recognition_time;
        """
        with get_db_cursor() as cursor:
            cursor.execute(query, (module, postgres_date))
            results = cursor.fetchall()

        if not results:
            return {"status": "success", "data": [], "message": "No records found for the specified module."}

        formatted_results = [format_recognition_row(row) for row in results]
        return {"status": "success", "data": formatted_results}

    except HTTPException as e:
        api_logger.warning(e)
        raise
    except Exception as e:
        api_logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.get("/fetch_frames_by_time")
def fetch_frames_by_time(
        date: str,
        module: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        api_key: bool = Depends(get_api_key)
):
    """
    Fetch recognition frames across all people for a given date,
    optionally within a specified time range, and return a tiled image.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")
    try:
        dt, postgres_date = parse_date(date)
        year = dt.year
        # Use the subpartition table named with the year and module.
        table_name = f"recognition_results_{year}_{module}"
        query = f"SELECT person_id, camera_name, camera_ip, recognition_frame, recognition_time FROM {table_name} WHERE recognition_date = %s"
        params = [postgres_date]

        if start_time:
            try:
                dt_start = datetime.strptime(start_time, "%I:%M %p")
                start_time_24 = dt_start.strftime("%H:%M:%S")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_time format. Please use 'HH:MM AM/PM'.")
            query += " AND recognition_time >= %s"
            params.append(start_time_24)
            if end_time:
                try:
                    dt_end = datetime.strptime(end_time, "%I:%M %p")
                    end_time_24 = dt_end.strftime("%H:%M:%S")
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid end_time format. Please use 'HH:MM AM/PM'.")
                if dt_end < dt_start:
                    raise HTTPException(status_code=400, detail="end_time cannot be less than start_time.")
                query += " AND recognition_time <= %s"
                params.append(end_time_24)

        query += " ORDER BY recognition_time"
        with get_db_cursor() as cursor:
            cursor.execute(query, tuple(params))
            results = cursor.fetchall()

        if not results:
            api_logger.warning("No data found for the specified date and time period.")
            raise HTTPException(status_code=404, detail="No data found for the specified date and time period.")

        frames, metadata = [], []
        for row in results:
            image, meta = decode_recognition_frame(row)
            if image is not None:
                meta = f"Person: {row.get('person_id')}\n{meta}"
                frames.append(image)
                metadata.append(meta)

        if not frames:
            api_logger.warning("No valid frames found for the specified date and time period.")
            raise HTTPException(status_code=404, detail="No valid frames found for the specified date and time period.")

        # Calculate grid dimensions (maximum 2 columns).
        num_frames = len(frames)
        cols_count = 2 if num_frames >= 2 else 1
        rows_count = int(np.ceil(num_frames / cols_count))

        fig_width = cols_count * (640 / 100)
        fig_height = rows_count * (360 / 100)
        fig, axes = plt.subplots(rows_count, cols_count, figsize=(fig_width, fig_height))
        axes = axes.flatten() if (rows_count * cols_count) > 1 else [axes]

        for i, ax in enumerate(axes):
            if i < num_frames:
                ax.imshow(frames[i])
                ax.axis("off")
                ax.text(
                    0.5, -0.02, metadata[i],
                    transform=ax.transAxes, ha="center", va="top",
                    fontsize=10, color="black",
                    bbox=dict(facecolor="white", alpha=0.7, pad=2)
                )
            else:
                ax.axis("off")

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close(fig)
        return StreamingResponse(buf, media_type="image/png")

    except HTTPException as e:
        api_logger.error(f"HTTP Exception occurred: {e}")
        raise
    except Exception as e:
        api_logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


@app.post("/manual_post")
def manual_post(
        date: str,
        location: str,
        api_key: bool = Depends(get_api_key)
):
    """
    Post all recognition data for a given date and location as a single batched request.
    API endpoint is determined from the location using camera config JSON.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")

    try:
        # Load camera configuration JSON
        with open(CAMERA_CONFIGURATION_FILE, "r") as file:
            config = json.load(file)

        if location not in config:
            raise HTTPException(status_code=404, detail=f"Location '{location}' not found in configuration.")

        api_endpoint = config[location].get("api-endpoint")
        if not api_endpoint:
            raise HTTPException(status_code=400, detail=f"API endpoint not defined for location '{location}'.")

        dt, postgres_date = parse_date(date)
        year = dt.year
        table_name = f"recognition_results_{year}_{location}"

        query = f"""
            SELECT id, person_id, camera_name, camera_ip, recognition_date, recognition_time,
                   confidence_score, location
            FROM {table_name}
            WHERE recognition_date = %s AND location = %s;
        """
        with get_db_cursor() as cursor:
            cursor.execute(query, (postgres_date, location))
            rows = cursor.fetchall()

        if not rows:
            return {"status": "error", "message": "No records found for the specified date and location."}

        payload_list = []
        row_id_list = []

        for row in rows:
            row_id_list.append(row.get("id"))
            payload_list.append({
                "entity": row.get("person_id"),
                "location": row.get("location"),
                "cam_name": row.get("camera_name"),
                "cam_ip": row.get("camera_ip"),
                "date": row.get("recognition_date").strftime("%d-%m-%Y")
                if hasattr(row.get("recognition_date"), "strftime") else row.get("recognition_date"),
                "time": row.get("recognition_time").strftime("%H:%M:%S")
                if hasattr(row.get("recognition_time"), "strftime") else row.get("recognition_time"),
                "similarity": float(row.get("confidence_score", 0)),
            })

        recognition_object = {"recognition": payload_list}

        # Send single batched POST request
        try:
            response = requests.post(api_endpoint, json=recognition_object, timeout=60)
            if response.status_code == 200:
                resp_json = response.json()
                data = resp_json.get("data")
                status = data.get("status", "") if data else ""

                if status.startswith("Status:") and status.endswith("Attendance Successfully Marked"):
                    for row_id in row_id_list:
                        update_api_acknowledged(row_id)
                    return {
                        "status": "success",
                        "message": f"Posted {len(row_id_list)} entries to {location} API.",
                        "response_status": status,
                        "recognition" : payload_list
                    }
                else:
                    return {
                        "status": "failed",
                        "message": f"Unexpected status: {status}",
                        "response": resp_json
                    }
            else:
                return {
                    "status": "failed",
                    "message": f"HTTP {response.status_code}: {response.reason}"
                }
        except Exception as e:
            api_logger.error(f"Exception posting batched data for location {location} - {e}")
            raise HTTPException(status_code=500, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Unexpected error in manual_post: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# -------------------- Main --------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
