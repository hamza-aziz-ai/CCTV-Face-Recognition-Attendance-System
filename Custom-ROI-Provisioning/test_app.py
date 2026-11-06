"""Checks for the ROI page with a fake camera and a sample camera configuration.
Run in the roi image: python3 Custom-ROI-Provisioning/test_app.py"""
import json
import os
import shutil
import sys
import tempfile
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import app  # noqa: E402

# The shape of src/Camera-Configuration/camera_configuration.example.json, which images do not ship
SAMPLE = {"maingate": {"api-endpoint": "https://ERP_HOST/attendance-endpoint", "cctv-cameras": {
    "entry": {f"cctv-camera-{i}": {"username": None, "password": None, "ip_address": f"10.0.0.{i}", "port": 554,
                                   "endpoint": "stream", "masking-coordinates": None, "cluster": "cluster-1"} for i in (1, 2)},
    "exit": {"cctv-camera-3": {"username": None, "password": None, "ip_address": "http://10.0.0.3/video", "port": None,
                               "endpoint": None, "masking-coordinates": [[0, 0], [10, 0], [10, 10]]}}}}}
CAMERA = "maingate/entry/cctv-camera-1"


def region(config):
    return config["maingate"]["cctv-cameras"]["entry"]["cctv-camera-1"]["masking-coordinates"]


def test():
    folder = tempfile.mkdtemp()
    config = os.path.join(folder, "camera_configuration.json")
    with open(config, "w") as f:
        json.dump(SAMPLE, f, indent=4)
    before = json.load(open(config))
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)  # a full-resolution frame from the fake camera

    with mock.patch.object(app, "CAMERA_CONFIGURATION_FILE", config), mock.patch.object(app, "snapshot", lambda camera: frame):
        client = app.app.test_client()
        page = client.get("/")
        assert page.status_code == 200 and b"Custom Region of Interest" in page.data
        ids =[c["id"] for c in client.get("/api/cameras").get_json()]
        assert CAMERA in ids and len(ids) == len(set(ids)), ids

        snap = client.get(f"/snapshot?camera={CAMERA}")
        assert snap.status_code == 200 and snap.mimetype == "image/jpeg"
        assert client.get("/snapshot?camera=nowhere/entry/x").status_code == 404

        square = [[100, 100], [500, 100], [500, 400], [100, 400]]
        preview = client.post("/preview", json={"camera": CAMERA, "points": square})
        assert preview.status_code == 200 and preview.mimetype == "image/jpeg"
        outside = client.post("/preview", json={"camera": CAMERA, "points": [[100, 100], [1500, 100], [1500, 400]]})
        assert outside.status_code == 400 and "1280x720" in outside.get_json()["error"], outside.get_json()

        # A region drawn on a 1920x1080 snapshot is refused now that the camera sends 1280x720, though the points fit it
        stale = client.post("/api/roi", json={"camera": CAMERA, "points": square, "size": [1920, 1080]})
        assert stale.status_code == 409 and "now sends 1280x720" in stale.get_json()["error"], stale.get_json()
        assert json.load(open(config)) == before, "a refused save changed nothing"

        saved = client.post("/api/roi", json={"camera": CAMERA, "points": square, "size": [1280, 720]})
        assert saved.status_code == 200, saved.get_json()
        after = json.load(open(config))
        entry = after["maingate"]["cctv-cameras"]["entry"]["cctv-camera-1"]
        assert region(after) == square and entry["masking-frame-size"] == [1280, 720]
        assert next(c for c in client.get("/api/cameras").get_json() if c["id"] == CAMERA)["size"] == [1280, 720]
        # Nothing but that one camera's region and its size changed
        entry["masking-coordinates"] = region(before)
        del entry["masking-frame-size"]
        assert after == before

        for size in ([0, 720], [1280], "x", [1280, True], [1280.0, 720]):
            assert client.post("/api/roi", json={"camera": CAMERA, "points": square, "size": size}).status_code == 400, size
        assert client.post("/api/roi", json={"camera": CAMERA, "points": square}).status_code == 400, "a save needs the snapshot size"
        beyond = [[100, 100], [1281, 100], [1281, 400]]
        assert client.post("/api/roi", json={"camera": CAMERA, "points": beyond, "size": [1280, 720]}).status_code == 400
        edge = [[0, 0], [1280, 0], [1280, 720]]
        assert client.post("/api/roi", json={"camera": CAMERA, "points": edge, "size": [1280, 720]}).status_code == 200
        assert client.post("/api/roi", json={"camera": CAMERA, "points": square, "size": [1280, 720]}).status_code == 200

        for bad in ([[1, 2], [3, 4]], [[1, 2], [3, "4"], [5, 6]], [[1, 2], [3, -4], [5, 6]], [[1, 2], [3, True], [5, 6]], "x"):
            assert client.post("/api/roi", json={"camera": CAMERA, "points": bad, "size": [1280, 720]}).status_code == 400, bad
        assert client.post("/api/roi", json={"camera": "maingate/entry/../x", "points": square, "size": [1280, 720]}).status_code == 400
        assert region(json.load(open(config))) == square, "a refused request changed nothing"

    def no_camera(camera):
        raise AssertionError("clearing a region must not open the camera")

    with mock.patch.object(app, "CAMERA_CONFIGURATION_FILE", config), mock.patch.object(app, "snapshot", no_camera):
        client = app.app.test_client()
        assert client.post("/api/roi", json={"camera": CAMERA, "points": None}).status_code == 200
        cleared = json.load(open(config))
        assert region(cleared) is None and "masking-frame-size" not in cleared["maingate"]["cctv-cameras"]["entry"]["cctv-camera-1"]
        assert sorted(os.listdir(folder)) == ["camera_configuration.json"], "no temporary file left behind"
    shutil.rmtree(folder)
    print("roi ok (cameras listed, snapshot and preview served, region saved with its snapshot size, stale size refused, bad input refused, cleared without the camera)")


if __name__ == "__main__":
    test()
