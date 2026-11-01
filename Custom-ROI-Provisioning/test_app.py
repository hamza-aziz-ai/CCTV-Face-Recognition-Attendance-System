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
                                   "endpoint": "stream", "masking-coordinates": None} for i in (1, 2)},
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

        saved = client.post("/api/roi", json={"camera": CAMERA, "points": square})
        assert saved.status_code == 200, saved.get_json()
        after = json.load(open(config))
        assert region(after) == square
        # Nothing but that one camera's region changed
        after["maingate"]["cctv-cameras"]["entry"]["cctv-camera-1"]["masking-coordinates"] = region(before)
        assert after == before

        for bad in ([[1, 2], [3, 4]], [[1, 2], [3, "4"], [5, 6]], [[1, 2], [3, -4], [5, 6]], [[1, 2], [3, True], [5, 6]], "x"):
            assert client.post("/api/roi", json={"camera": CAMERA, "points": bad}).status_code == 400, bad
        assert client.post("/api/roi", json={"camera": "maingate/entry/../x", "points": square}).status_code == 400
        assert region(json.load(open(config))) == square, "a refused request changed nothing"

        assert client.post("/api/roi", json={"camera": CAMERA, "points": None}).status_code == 200
        assert region(json.load(open(config))) is None
        assert sorted(os.listdir(folder)) == ["camera_configuration.json"], "no temporary file left behind"
    shutil.rmtree(folder)
    print("roi ok (cameras listed, snapshot and preview served, region saved alone, bad input refused, cleared)")


if __name__ == "__main__":
    test()
