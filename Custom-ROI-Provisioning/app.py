"""
Draws each camera's region of interest (ROI) and saves it to the site's camera configuration.

The producer crops every frame to the camera's `masking-coordinates` polygon before recognition
(src/util/generic_utilities.py: crop_and_mask_roi). This page shows a full-resolution snapshot of a camera, lets you
click the polygon on it, previews the crop with the producer's own function, and saves the points to
src/Camera-Configuration/camera_configuration.json. The producer reads that file at start, so restart it afterwards.
The points are pixels of the snapshot, so its size is saved with them as `masking-frame-size`, and only when a fresh frame
from the camera still has that size: the producer then refuses the region if the camera's resolution later changes.

It is served inside the website at /roi/ for client admins (D-035 addendum). It asks this client's API about every request
(ROI_AUTH_URL) instead of trusting the proxy: the service sits on the proxy network every client's stack shares, so other
containers can reach it directly. The API checks the session cookie, the role and, for a write, the CSRF token.

Author: Kshitij Parashar
Date: 4 October 2023
Rewritten 2026-10-31: the old page edited src/parameters.py and imported names that no longer exist.
"""
import json
import logging
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

import cv2
from flask import Flask, Response, g, jsonify, redirect, render_template, request

# The shared modules live in src/ and import each other by bare name (`from parameters import ...`)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src"))

from parameters import CAMERA_CONFIGURATION_FILE, ROI_AUTH_URL  # noqa: E402
from util.generic_utilities import camera_stream_url, crop_and_mask_roi  # noqa: E402

MAX_POINTS = 100
MAX_COORDINATE = 20000  # well above any camera resolution in use
# Camera opens are bounded in time (video_source's limits) and in number: a dead camera cannot pile up requests
OPEN_TIMEOUT_MS, READ_TIMEOUT_MS = 10000, 5000
captures = threading.BoundedSemaphore(2)
# ponytail: one lock in one process (the Flask server); a multi-worker server needs a file lock around the same code
saving = threading.Lock()

app = Flask(__name__)
audit = logging.getLogger("roi.audit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None  # a redirect is not a 204: refused


auth = urllib.request.build_opener(NoRedirect)


def check_admin():
    """The API's answer for this request: 204 (with the account), 401 signed out, 403 refused, else unavailable."""
    ask = urllib.request.Request(ROI_AUTH_URL, headers={
        "Cookie": request.headers.get("Cookie", ""), "X-CSRF-Token": request.headers.get("X-CSRF-Token", ""),
        "X-Forwarded-Method": request.method})  # this request's own method, never the caller's header
    try:
        with auth.open(ask, timeout=3) as answer:
            return answer.status, answer.headers.get("X-Account")
    except urllib.error.HTTPError as e:
        return e.code, None
    except OSError:
        return 503, None


@app.before_request
def admins_only():
    if request.path == "/health":
        return None
    status, account = check_admin()
    if status == 204 and account:
        g.account = account
        return None
    if status == 401:
        if request.method == "GET" and request.path == "/":
            return redirect("/auth/sign-in")
        return jsonify(error="Sign in again"), 401
    if status == 403:
        return jsonify(error="Only a client admin can change camera regions"), 403
    return jsonify(error="The sign-in check is unavailable; try again shortly"), 503


@app.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"  # camera pictures and the configuration
    return response


@app.get("/health")
def health():
    return jsonify(status="ok")


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


def valid_size(size):
    """[width, height] of the snapshot the points were drawn on."""
    if (not isinstance(size, list) or len(size) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) and 0 < v <= MAX_COORDINATE for v in size)):
        raise ValueError(f"not a snapshot size: {size!r}")
    return size


def valid_points(points, size=(MAX_COORDINATE, MAX_COORDINATE)):
    """A polygon as the producer expects it: at least 3 [x, y] integer points inside the frame (its right and bottom
    edges included)."""
    if not isinstance(points, list) or not 3 <= len(points) <= MAX_POINTS:
        raise ValueError(f"a region needs 3 to {MAX_POINTS} points")
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= limit for v, limit in zip(point, size))):
            raise ValueError(f"not a point inside the frame: {point!r}")
    return points


def save_points(camera_id, points, size=None):
    """Set one camera's masking-coordinates and the masking-frame-size they were drawn on (points None clears both).
    Written to a temporary file in the same folder and swapped in, so a crash never leaves a half-written configuration
    for the producer. One save at a time, or two saves for different cameras could each write back the other's old file."""
    with saving:
        write_points(camera_id, points, size)


def write_points(camera_id, points, size):
    config = load_config()
    camera = find_camera(config, camera_id)
    camera["masking-coordinates"] = points
    if points is None:
        camera.pop("masking-frame-size", None)
    else:
        camera["masking-frame-size"] = size
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
    if not captures.acquire(blocking=False):
        raise ConnectionError("the page is already reading from cameras; try again in a moment")
    try:
        stream = cv2.VideoCapture(camera_stream_url(camera), cv2.CAP_FFMPEG,
                                  [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS])
        try:
            grabbed, frame = stream.read()
        finally:
            stream.release()
    finally:
        captures.release()
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
    return jsonify([{"id": cid, "points": camera.get("masking-coordinates"), "size": camera.get("masking-frame-size")}
                    for cid, camera in cameras(load_config())])


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


class SizeChanged(ValueError):
    pass


def current_size(camera, drawn):
    """The camera's frame size now, which must still be the size of the snapshot the region was drawn on: saving old
    points with a new size would hide exactly the change the size is there to catch."""
    height, width = snapshot(camera).shape[:2]
    if [width, height] != drawn:
        raise SizeChanged(f"the camera now sends {width}x{height}, but the region was drawn on a {drawn[0]}x{drawn[1]} "
                          "snapshot. Load a new snapshot and draw it again")
    return drawn


@app.post("/api/roi")
def update_roi():
    """Save (or, with points null, clear) one camera's region. Saving needs the size of the snapshot it was drawn on,
    checked against a fresh frame; clearing needs no camera."""
    body = request.get_json(silent=True) or {}
    try:
        camera_id = body.get("camera", "")
        if body.get("points") is None:
            find_camera(load_config(), camera_id)
            save_points(camera_id, None)
        else:
            size = valid_size(body.get("size"))
            points = valid_points(body.get("points"), size)
            save_points(camera_id, points, current_size(find_camera(load_config(), camera_id), size))
    except SizeChanged as e:
        return jsonify(error=str(e)), 409
    except (KeyError, ValueError) as e:
        return jsonify(error=str(e)), 400
    except ConnectionError as e:
        return jsonify(error=str(e)), 502
    audit.info("region %s for %s by %s%s", "cleared" if body.get("points") is None else "saved", camera_id, g.account,
               "" if body.get("points") is None else f", {len(body['points'])} points on {body['size'][0]}x{body['size'][1]}")
    return jsonify(saved=camera_id, note="Saved, not applied yet: on an edge node, copy the camera configuration there "
                                         "first, then restart producer-consumer and the two controllers.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8069)
