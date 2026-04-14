"""
This module is created to make an API for the Face Liveness Detection Model.

Date: 12 December 2023
Author: Hamza Aziz
"""
import base64
from typing import List

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from face_spoofing_detection import face_liveness_detection

app = FastAPI()


class FramePayLoad(BaseModel):
    person_id: str
    faces: List[str]


@app.post("/liveness_detection/")
async def liveness_detection(payload: FramePayLoad):
    # print(payload)
    try:
        batch_of_faces = []
        for face in payload.faces:
            face_data = base64.b64decode(face)
            np_array = np.frombuffer(face_data, np.uint8)
            face = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
            batch_of_faces.append(face)

        # print(batch_of_faces)

        batch_result = face_liveness_detection(payload.person_id, batch_of_faces)

        if batch_result is None:
            batch_result = []

        # print(batch_result)

        return JSONResponse(content=batch_result, status_code=200)

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        return JSONResponse(content={"error": error_message}, status_code=500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=6969)
