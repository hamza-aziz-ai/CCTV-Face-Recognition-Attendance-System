import base64
import math
import os
import sys
from typing import List, Tuple

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from face_saver import save_face_if_better
from postgresql_database_handler import initialize_database_and_tables

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from custom_logging import dynamic_face_data_collector_logger as logger


class FaceRecord(BaseModel):
    person_id: str = Field(..., description="Unique identifier for the person")
    camera_name: str = Field(..., description="Name of the camera source")
    match_score: float = Field(..., description="Face matching score")
    landmarks: List[Tuple[int, int]] = Field(
        ..., description="List of at least two (x, y) pupil landmarks"
    )
    image_base64: str = Field(..., description="Base64-encoded cropped face image")


app = FastAPI(
    title="Dynamic Face Data Collector API (List Input)",
    description="Accepts JSON list of face crop records for dynamic face data collection.",
    version="2.0.0"
)


@app.post("/faces", summary="Submit multiple face crop records")
async def submit_faces(records: List[FaceRecord]) -> JSONResponse:
    failed = []
    for idx, record in enumerate(records):
        try:
            if len(record.landmarks) < 2:
                raise ValueError("At least two landmarks are required")

            # Decode image
            try:
                image_data = base64.b64decode(record.image_base64)
                np_arr = np.frombuffer(image_data, np.uint8)
                face_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if face_image is None:
                    raise ValueError("Decoded image is None")
            except Exception as e:
                raise ValueError(f"Invalid base64 image: {e}")

            # Pupil distance
            (x1, y1), (x2, y2) = record.landmarks[0], record.landmarks[1]
            pupil_distance = math.hypot(x2 - x1, y2 - y1)

            # Save the face
            save_face_if_better(
                person_id=record.person_id,
                camera_name=record.camera_name,
                face_crop=face_image,
                pupil_distance=pupil_distance,
                face_matching_score=record.match_score,
            )
        except Exception as e:
            logger.error(f"Failed to process record #{idx} ({record.person_id}): {e}")
            failed.append({"index": idx, "person_id": record.person_id, "error": str(e)})

    if failed:
        return JSONResponse(
            status_code=207,
            content={
                "message": f"{len(records) - len(failed)} succeeded, {len(failed)} failed",
                "failures": failed
            },
        )
    else:
        return JSONResponse(
            status_code=200,
            content={"message": f"All {len(records)} face records submitted successfully."},
        )


if __name__ == "__main__":
    import uvicorn

    initialize_database_and_tables()
    logger.info("Starting dynamic facial dataset collector (List-based API)")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
