"""
Draws each camera's region of interest (ROI) and saves it to the site's camera configuration.

The producer crops every frame to the camera's `masking-coordinates` polygon before recognition
(src/util/generic_utilities.py: crop_and_mask_roi). This page shows a full-resolution snapshot of a camera, lets you
click the polygon on it, previews the crop with the producer's own function, and saves the points to
src/Camera-Configuration/camera_configuration.json. The producer reads that file at start, so restart it afterwards.

Author: Kshitij Parashar
Date: 4 October 2023
Rewritten 2026-10-31: the old page edited src/parameters.py and imported names that no longer exist.
"""
import json
import os
import sys
import tempfile

import cv2
from flask import Flask, Response, jsonify, render_template, request

# The shared modules live in src/ and import each other by bare name (`from parameters import ...`)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src"))

from parameters import CAMERA_CONFIGURATION_FILE  # noqa: E402
from util.generic_utilities import camera_stream_url, crop_and_mask_roi  # noqa: E402

MAX_POINTS = 100
MAX_COORDINATE = 20000  # well above any camera resolution in use

app = Flask(__name__)


def load_config():
    with open(CAMERA_CONFIGURATION_FILE, encoding="utf-8") as f:
        return json.load(f)


def cameras(config):
    """Every camera as (id, its config), where id is "<location>/<entry or exit>/<camera name>"."""
    for location, settings in config.items():
        for point, named in settings.get("cctv-cameras", {}).items():
            for name, camera in named.items():
                yield f"{location}/{point}/{name}", camera


def find_camera(config, camera_id):
    for cid, camera in cameras(config):
        if cid == camera_id:
            return camera
    raise KeyError(f"no camera {camera_id!r} in the camera configuration")


def valid_points(points):
    """A polygon as the producer expects it: at least 3 [x, y] integer points inside the frame."""
    if not isinstance(points, list) or not 3 <= len(points) <= MAX_POINTS:
        raise ValueError(f"a region needs 3 to {MAX_POINTS} points")
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= MAX_COORDINATE for v in point)):
            raise ValueError(f"not a point inside the frame: {point!r}")
    return points


def save_points(camera_id, points):
    """Set one camera's masking-coordinates (None clears it). Written to a temporary file in the same folder and
    swapped in, so a crash never leaves a half-written configuration for the producer."""
    config = load_config()
    find_camera(config, camera_id)["masking-coordinates"] = None if points is None else valid_points(points)
    folder = os.path.dirname(os.path.abspath(CAMERA_CONFIGURATION_FILE))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, CAMERA_CONFIGURATION_FILE)
    except BaseException:
        os.unlink(tmp)
        raise


def snapshot(camera):
    """One frame at the camera's full resolution: the coordinates the producer's crop uses."""
    stream = cv2.VideoCapture(camera_stream_url(camera))
    try:
        grabbed, frame = stream.read()
    finally:
        stream.release()
    if not grabbed:
        raise ConnectionError("could not read a frame from the camera")
    return frame


def jpeg(frame):
    return Response(cv2.imencode(".jpg", frame)[1].tobytes(), mimetype="image/jpeg")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/cameras")
def list_cameras():
    return jsonify([{"id": cid, "points": camera.get("masking-coordinates")} for cid, camera in cameras(load_config())])


@app.get("/snapshot")
def camera_snapshot():
    try:
        return jpeg(snapshot(find_camera(load_config(), request.args.get("camera", ""))))
    except KeyError as e:
        return jsonify(error=str(e)), 404
    except ConnectionError as e:
        return jsonify(error=str(e)), 502


@app.post("/preview")
def preview():
    """The snapshot cropped and masked exactly as the producer would do it with these points."""
    body = request.get_json(silent=True) or {}
    try:
        points = valid_points(body.get("points"))
        return jpeg(crop_and_mask_roi(snapshot(find_camera(load_config(), body.get("camera", ""))), points))
    except (KeyError, ValueError) as e:
        return jsonify(error=str(e)), 400
    except ConnectionError as e:
        return jsonify(error=str(e)), 502


@app.post("/api/roi")
def update_roi():
    """Save (or, with points null, clear) one camera's region."""
    body = request.get_json(silent=True) or {}
    try:
        save_points(body.get("camera", ""), body.get("points"))
    except (KeyError, ValueError) as e:
        return jsonify(error=str(e)), 400
    return jsonify(saved=body.get("camera"), note="Restart producer-consumer to apply it.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8069)
