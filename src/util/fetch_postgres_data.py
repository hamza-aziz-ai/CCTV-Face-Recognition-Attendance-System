from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyQuery
from psycopg2 import connect, sql
from psycopg2.extras import RealDictCursor
import matplotlib.pyplot as plt
from apscheduler.schedulers.background import BackgroundScheduler
import numpy as np
import io
import os
import requests
from datetime import datetime
from generic_utilities import map_camera_to_api_endpoint

app = FastAPI()
CAMERA_TO_API_MAP = map_camera_to_api_endpoint()

# Database configuration
DB_CONFIG = {
    'dbname': os.environ.get("POSTGRESQL_DATABASE", "facial_recognition_results"),
    'user': os.environ.get("POSTGRESQL_USERNAME", "postgres"),
    'password': os.environ.get("POSTGRESQL_PASSWORD"),
    'host': os.environ.get("POSTGRESQL_HOST", "localhost"),
    'port': os.environ.get("POSTGRESQL_PORT", "5432")
}

# API key for authentication
API_KEY = os.environ["API_KEY"]
api_key_query = APIKeyQuery(name="api_key")


def fetch_unacknowledged_rows():
    """
    Fetch rows where api_acknowledged is False.
    """
    try:
        connection = connect(**DB_CONFIG)
        cursor = connection.cursor(cursor_factory=RealDictCursor)

        # Query to fetch unacknowledged rows
        cursor.execute("""
            SELECT id, person_id, camera_name, camera_ip, recognition_date, recognition_time, confidence_score
            FROM recognition_results
            WHERE api_acknowledged = false;
        """)
        rows = cursor.fetchall()

        cursor.close()
        connection.close()

        return rows

    except Exception as e:
        print(f"Error fetching unacknowledged rows: {e}")
        return []


def update_api_acknowledged(row_id):
    """
    Update api_acknowledged to True for the given row ID.
    """
    try:
        connection = connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Update the row
        cursor.execute("""
            UPDATE recognition_results
            SET api_acknowledged = true
            WHERE id = %s;
        """, (row_id,))

        connection.commit()
        cursor.close()
        connection.close()

    except Exception as e:
        print(f"Error updating api_acknowledged for row {row_id}: {e}")



def post_to_api(row):
    """
    Post data to the mapped API endpoint and update the database if successful.
    """
    # Map the camera to the API
    camera_name = row['camera_name']
    api_endpoint = CAMERA_TO_API_MAP.get(camera_name)
    if not api_endpoint:
        print(f"No API endpoint mapped for camera: {row['camera_name']}")
        return

    # Prepare the payload
    payload = {
        "entity": row["person_id"],
        "location": row["camera_name"],
        "cam_ip": row["camera_ip"],
        "date": row["recognition_date"].strftime("%d-%m-%Y"),
        "time": row["recognition_time"].strftime("%H:%M:%S"),
        "similarity": float(row["confidence_score"])
    }

    try:
        # Post data to the API
        response = requests.post(api_endpoint, json=payload, timeout=10)

        if response.status_code == 200:
            print(f"Data posted successfully for row ID {row['id']}.")
            update_api_acknowledged(row["id"])
        else:
            print(f"Failed to post data for row ID {row['id']}: {response.status_code} {response.reason}")

    except Exception as e:
        print(f"Error posting data for row ID {row['id']}: {e}")


def process_unacknowledged_rows():
    """
    Process all unacknowledged rows periodically.
    """
    rows = fetch_unacknowledged_rows()
    if not rows:
        print("No unacknowledged rows found.")
        return

    print(f"Found {len(rows)} unacknowledged rows. Processing...")
    for row in rows:
        post_to_api(row)


@app.on_event("startup")
def start_scheduler():
    """
    Start the APScheduler to process unacknowledged rows periodically.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(process_unacknowledged_rows, "interval", minutes=1)
    scheduler.start()
    print("Scheduler started to process unacknowledged rows every minute.")


def get_api_key(api_key: str = Depends(api_key_query)):
    """
    Validates the provided API key.

    Parameters:
        api_key (str): API key provided in the request.

    Returns:
        bool: True if the API key is valid, otherwise raises an HTTPException.
    """
    if api_key == API_KEY:
        return True
    raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")


@app.get("/fetch_tiled_frames")
def fetch_tiled_frames(
        date: str,
        person_id: str,
        api_key: bool = Depends(get_api_key)
):
    """
    Fetch all recognition frames for a given person_id on a specific date
    and return a tiled display of the frames.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")

    try:
        # Convert the input date from DD-MM-YYYY to YYYY-MM-DD
        try:
            input_date = datetime.strptime(date, "%d-%m-%Y")
            postgres_date = input_date.strftime("%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Please use 'DD-MM-YYYY'.")

        # Connect to the database
        connection = connect(**DB_CONFIG)
        cursor = connection.cursor(cursor_factory=RealDictCursor)

        # Query to fetch frames for the given date and person_id
        query = sql.SQL("""
            SELECT camera_name, camera_ip, recognition_time, recognition_frame
            FROM recognition_results
            WHERE recognition_date = %s AND person_id = %s;
        """)
        cursor.execute(query, (postgres_date, person_id))
        results = cursor.fetchall()
        # print(results)

        # Close the connection
        cursor.close()
        connection.close()

        # Check if any frames were found
        if not results:
            raise HTTPException(status_code=404, detail="No frames found for the specified date and person_id.")

        # Extract and decode frames, skipping NULL or invalid frames
        frames = []
        metadata = []  # Store camera_name and camera_ip for each frame
        for row in results:
            recognition_frame = row["recognition_frame"]
            recognition_time = datetime.strptime(str(row['recognition_time']), "%H:%M:%S")
            if recognition_frame is not None:
                try:
                    # Decode memoryview to bytes if necessary
                    if isinstance(recognition_frame, memoryview):
                        recognition_frame = recognition_frame.tobytes()
                    # Read the image into a NumPy array
                    image = plt.imread(io.BytesIO(recognition_frame), format="JPEG")
                    frames.append(image)
                    metadata.append(f"Time: {recognition_time.strftime('%I:%M:%S %p')} | Camera Info: {row['camera_name']} ({row['camera_ip']})")
                except Exception as e:
                    # Log and skip invalid frames
                    print(f"Error decoding frame: {e}")
                    continue

        # Check if valid frames exist
        if not frames:
            raise HTTPException(status_code=404, detail="No valid frames found for the specified date and person_id.")

        # Create a tiled display of the frames
        num_frames = len(frames)
        # Calculate grid size dynamically
        rows = int(np.ceil(np.sqrt(num_frames)))
        cols = int(np.ceil(num_frames / rows))  # Ensure enough columns for all frames

        # Calculate figsize to maintain at least 640x360 per frame
        fig_width = cols * (640 / 100)  # Convert pixels to inches (1 inch = 100 px approx)
        fig_height = rows * (360 / 100)
        fig, axes = plt.subplots(rows, cols, figsize=(fig_width, fig_height))

        # Flatten axes array for easy indexing, even if the grid is not fully populated
        axes = axes.flatten() if num_frames > 1 else [axes]

        for i, ax in enumerate(axes):
            if i < num_frames:
                ax.imshow(frames[i])
                ax.axis("off")  # Remove axes for cleaner display
                # Overlay camera_name, camera_ip, and recognition_time at the bottom of the frame
                ax.text(
                    0.5, -0.02, metadata[i], transform=ax.transAxes,
                    ha="center", va="top", fontsize=10, color="black",
                    bbox=dict(facecolor="white", alpha=0.7, pad=2)
                )
            else:
                ax.axis("off")  # Hide unused subplots

        # Save the figure to a BytesIO buffer
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)

        # Return the tiled image as a response
        return StreamingResponse(buf, media_type="image/png")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


@app.get("/fetch_data")
def fetch_data(
        date: str,
        person_id: str = None,
        camera_name: str = None,
        confidence_score: float = Query(None, ge=0, le=100),
        api_acknowledged: bool = None,
        api_key: bool = Depends(get_api_key)
):
    """
    Fetch data from the database for a given date and format the results.
    Only authorized users with valid API keys can access this endpoint.

    Parameters:
        date (str): Date in 'DD-MM-YYYY' format.
        person_id (str): Optional filter for person ID.
        camera_name (str): Optional filter for camera name.
        confidence_score (float): Optional filter for confidence score (0 to 100).
        api_acknowledged (bool): Optional filter for API acknowledgment status.
        api_key (bool): Dependency that validates the API key.

    Returns:
        JSON: Recognition results with formatted date, time, and confidence score.
    """
    if not api_key:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid API Key")

    try:
        # Validate the input date
        try:
            input_date = datetime.strptime(date, "%d-%m-%Y")
            postgres_date = input_date.strftime("%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Please use 'YYYY-MM-DD'.")

        # Ensure the date is not in the future
        today = datetime.now().date()
        if input_date.date() > today:
            raise HTTPException(status_code=400, detail="Future dates are not allowed. Please provide a past or present date.")

        # Connect to the database
        connection = connect(**DB_CONFIG)
        cursor = connection.cursor(cursor_factory=RealDictCursor)

        # Build the SQL query dynamically
        query = sql.SQL("""
            SELECT id, person_id, camera_name, camera_ip, recognition_date, recognition_time,
                   confidence_score, api_acknowledged
            FROM recognition_results
            WHERE recognition_date = %s
        """)
        query_params = [postgres_date]

        if person_id:
            query += sql.SQL(" AND person_id = %s")
            query_params.append(person_id)
        if camera_name:
            query += sql.SQL(" AND camera_name = %s")
            query_params.append(camera_name)
        if confidence_score is not None:
            query += sql.SQL(" AND confidence_score >= %s")
            query_params.append(confidence_score)
        if api_acknowledged is not None:
            query += sql.SQL(" AND api_acknowledged = %s")
            query_params.append(api_acknowledged)

        # Connect to the database
        cursor.execute(query, query_params)
        results = cursor.fetchall()

        # Close the connection
        cursor.close()
        connection.close()

        # Return no records found if the result set is empty
        if not results:
            return {"status": "success", "data": [], "message": "No records found for the specified date."}

        # Format the results
        formatted_results = []
        for row in results:
            recognition_date = datetime.strptime(str(row['recognition_date']), "%Y-%m-%d")
            recognition_time = datetime.strptime(str(row['recognition_time']), "%H:%M:%S")
            formatted_results.append({
                "person_id": row["person_id"],
                "camera_name": row["camera_name"],
                "camera_ip": row["camera_ip"],
                "recognition_date": recognition_date.strftime("%d %B %Y, %A"),  # e.g., "2 February 2025, Sunday"
                "recognition_time": recognition_time.strftime("%I:%M:%S %p"),  # e.g., "02:30:45 PM"
                "confidence_score": f"{row['confidence_score']:.2f}%",  # e.g., "98.76%"
                "api_acknowledged": row["api_acknowledged"]
            })

        return {"status": "success", "data": formatted_results}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8023)
