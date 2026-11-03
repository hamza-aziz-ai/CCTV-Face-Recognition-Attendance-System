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

from parameters import DISPLAY_FACE_IMAGE_SERVER_PORT, POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login

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


def names_for(ids: List[str]) -> dict:
    """Each ID's registered name from this client's persons table (D-048), or None. Best-effort: the display shows the
    ID alone when a name is missing, so any database problem answers None for all."""
    import psycopg2
    found = {}
    try:
        user, password = postgres_login()
        with psycopg2.connect(dbname=POSTGRESQL_DATABASE, user=user, password=password, host=POSTGRESQL_HOST,
                              port=POSTGRESQL_PORT, connect_timeout=3) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT person_id, name FROM persons WHERE person_id = ANY(%s)", (list(ids),))
            found = dict(cursor.fetchall())
    except Exception as error:
        # Never the names themselves: the log says only why the lookup failed
        print(f"Name lookup failed for {len(ids)} ID(s): {type(error).__name__}", flush=True)
    return {person_id: found.get(person_id) for person_id in ids}


@app.post("/post_names")
def get_names(request: ImageRequest):
    """For the display (owner, 2026-11-03): the ID is shown large and the name beneath it. Every requested ID is in the
    reply, with its name as a plain string or null; names are never logged."""
    return names_for(request.messages[:100])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=DISPLAY_FACE_IMAGE_SERVER_PORT)
