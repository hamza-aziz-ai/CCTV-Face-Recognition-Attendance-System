import base64
from fastapi import FastAPI
from typing import List
import numpy as np
from get_front_face_image import get_image_by_id
import cv2
import os
import sys
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import DISPLAY_FACE_IMAGE_SERVER_PORT

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImageRequest(BaseModel):
    messages: List[str]


@app.post("/post_images")
async def get_images(request: ImageRequest):
    # print(request.messages)
    results = get_image_by_id(request.messages)

    # Convert images to base64 strings for JSON compatibility
    for result in results:
        for id_key, image_value in result.items():
            if isinstance(image_value, np.ndarray) and id_key != "ERROR" and id_key != "SUCCESS":
                _, encoded_image_value = cv2.imencode('.jpg', image_value)
                decoded_image_value = base64.b64encode(encoded_image_value.tobytes()).decode('utf-8')
                image_value = decoded_image_value
            result[id_key] = image_value

    return results


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=DISPLAY_FACE_IMAGE_SERVER_PORT)
