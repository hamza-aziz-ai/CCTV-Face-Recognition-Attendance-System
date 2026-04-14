import json
import os
import sys

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Add parent directory to the path to allow relative imports.
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import DATABASE_PORT, CAMERA_CONFIGURATION_FILE
from custom_logging import database_server_logger
from postgresql_database import insert_recognition_data, initialize_database_and_partitions

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
async def ingest_data(payload: RecognitionPayload, background_tasks: BackgroundTasks):
    """
    Ingest recognition data sent from a client.

    The payload should contain:
      - current_date (YYYY-MM-DD)
      - current_time (HH:MM:SS)
      - results (a dictionary which may include Base64‑encoded frame data)

    The insertion into the database is scheduled as a background task.
    """
    # Validate payload contents.
    if not (payload.current_date and payload.current_time and payload.results):
        msg = "Invalid payload: missing one or more required keys ('current_date', 'current_time', 'results')."
        database_server_logger.error(msg)
        raise HTTPException(status_code=400, detail=msg)

    try:
        # Schedule the database insertion in the background so that we can respond quickly.
        background_tasks.add_task(
            insert_recognition_data, payload.current_date, payload.current_time, payload.results
        )
        database_server_logger.info(f"Received data for {payload.current_date} {payload.current_time}. Insertion scheduled.")
    except Exception as e:
        database_server_logger.error(f"Error scheduling background task for data insertion: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

    # Return an immediate acknowledgment.
    return {"status": "OK"}

if __name__ == "__main__":
    # Run the FastAPI app with Uvicorn. Using DATABASE_PORT as the server port.
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DATABASE_PORT)
