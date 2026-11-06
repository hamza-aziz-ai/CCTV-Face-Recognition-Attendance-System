import json
import os
import sys
import threading
import time

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add parent directory to the path to allow relative imports.
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import DATABASE_PORT, CAMERA_CONFIGURATION_FILE
from custom_logging import database_server_logger
from postgresql_database import insert_recognition_data, initialize_database_and_partitions, write_health

# Define a Pydantic model for the expected JSON payload.
class RecognitionPayload(BaseModel):
    current_date: str
    current_time: str
    results: dict

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """
    Load camera configuration and initialize the database/schemas on startup.
    """
    try:
        with open(CAMERA_CONFIGURATION_FILE, "r") as config_file:
            camera_config_data = json.load(config_file)
        initialize_database_and_partitions(camera_config_data)
        database_server_logger.info("Database and schemas initialized successfully.")
    except Exception as e:
        database_server_logger.error(f"Error during startup initialization: {e}")
        # If startup initialization fails, you may want to stop the application.
        raise e

@app.post("/ingest")
def ingest_data(payload: RecognitionPayload):
    """Saves one batch of recognition records (current_date YYYY-MM-DD, current_time HH:MM:SS, results) and answers only
    once it is committed. `committed: true` tells a sender the records are saved; a sender must not treat a plain 200 as
    saved, since older releases answered before writing. A bad payload gets 400 and is never worth sending again; a
    database failure gets 503, nothing of the batch is saved, and the same batch may be sent again unchanged."""
    try:
        inserted, deduplicated = insert_recognition_data(payload.current_date, payload.current_time, payload.results)
    except ValueError as error:
        database_server_logger.error(f"Refused a batch of {payload.current_date} {payload.current_time}: {error}")
        raise HTTPException(status_code=400, detail=str(error))
    except psycopg2.Error as error:
        database_server_logger.error(f"Batch of {payload.current_date} {payload.current_time} not saved: "
                                     f"{type(error).__name__} {getattr(error, 'pgcode', None)}")
        raise HTTPException(status_code=503, detail="database unavailable; nothing of the batch was saved")
    return {"status": "OK", "committed": True, "inserted": inserted, "deduplicated": deduplicated}


# The database's own proof that it takes writes, also when nobody is being recognised. Only the latest write counts: a
# failed one, or one still running past its deadline, cancels the success before it
HEALTH_SECONDS = 30
HEALTH_DEADLINE = 10
HEALTH_MAX_AGE = 90
health = {"started": None, "saved_at": None, "failed": False}


def health_writer():
    while True:
        health["started"] = time.monotonic()
        try:
            write_health()
            health.update(saved_at=time.monotonic(), failed=False)
        except Exception as error:
            health["failed"] = True
            database_server_logger.error(f"Health write failed: {type(error).__name__} {getattr(error, 'pgcode', None)}")
        health["started"] = None
        time.sleep(HEALTH_SECONDS)


def database_writable(now=None):
    now = time.monotonic() if now is None else now
    started, saved_at = health["started"], health["saved_at"]
    if health["failed"] or saved_at is None or (started is not None and now - started > HEALTH_DEADLINE):
        return False
    return now - saved_at <= HEALTH_MAX_AGE


@app.on_event("startup")
async def start_health_writer():
    threading.Thread(target=health_writer, daemon=True).start()


@app.get("/health")
def service_health():
    if database_writable():
        return {"status": "ready"}
    return JSONResponse({"status": "unready", "reason": "database_write_failing"}, status_code=503)


if __name__ == "__main__":
    # Run the FastAPI app with Uvicorn. Using DATABASE_PORT as the server port.
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DATABASE_PORT)
