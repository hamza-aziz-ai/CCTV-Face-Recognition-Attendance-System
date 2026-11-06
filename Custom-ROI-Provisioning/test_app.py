"""Checks for the ROI page with a fake camera and a sample camera configuration, and its gate: a stand-in for the API's
/auth/check-admin decides every request.
Run in the roi image: python3 Custom-ROI-Provisioning/test_app.py"""
import http.server
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
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

    with mock.patch.object(app, "CAMERA_CONFIGURATION_FILE", config), mock.patch.object(app, "snapshot", lambda camera: frame),             mock.patch.object(app, "check_admin", lambda: (204, "boss")):
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

    with mock.patch.object(app, "CAMERA_CONFIGURATION_FILE", config), mock.patch.object(app, "snapshot", no_camera),             mock.patch.object(app, "check_admin", lambda: (204, "boss")):
        client = app.app.test_client()
        assert client.post("/api/roi", json={"camera": CAMERA, "points": None}).status_code == 200
        cleared = json.load(open(config))
        assert region(cleared) is None and "masking-frame-size" not in cleared["maingate"]["cctv-cameras"]["entry"]["cctv-camera-1"]
        assert sorted(os.listdir(folder)) == ["camera_configuration.json"], "no temporary file left behind"
    shutil.rmtree(folder)
    print("roi ok (cameras listed, snapshot and preview served, region saved with its snapshot size, stale size refused, bad input refused, cleared without the camera)")


def test_gate():
    """Every request but /health waits for the API's answer; the method sent is the request's own, never a header the
    caller set; no answer, a redirect or anything but 204 refuses it, before any camera or file is touched."""
    seen, answer = [], {"status": 204}

    class Api(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers)  # case-insensitive, as HTTP headers are
            self.send_response(answer["status"])
            if answer["status"] == 204:
                self.send_header("X-Account", "boss")
            if answer["status"] == 302:
                self.send_header("Location", "/elsewhere")
            self.end_headers()

        def log_message(self, *args):
            pass

    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=api.serve_forever, daemon=True).start()

    def no_camera(camera):
        raise AssertionError("a refused request must not open a camera")

    with mock.patch.object(app, "ROI_AUTH_URL", f"http://127.0.0.1:{api.server_port}/auth/check-admin"),             mock.patch.object(app, "snapshot", no_camera):
        client = app.app.test_client()
        assert client.get("/health").status_code == 200 and not seen, "the healthcheck needs no sign-in and asks nobody"
        client.set_cookie("__Host-session", "s")
        page = client.get("/", headers={"X-Forwarded-Method": "GET"})
        assert page.status_code == 200 and page.headers["Cache-Control"] == "no-store"
        assert seen[-1].get("Cookie") == "__Host-session=s" and seen[-1].get("X-Forwarded-Method") == "GET", dict(seen[-1])
        client.post("/api/roi", json={}, headers={"X-Forwarded-Method": "GET", "X-CSRF-Token": "t"})
        assert seen[-1].get("X-Forwarded-Method") == "POST" and seen[-1].get("X-CSRF-Token") == "t", "a forged method header is not relayed"
        for status, expected in ((401, 401), (403, 403), (500, 503), (302, 503)):
            answer["status"] = status
            assert client.post("/api/roi", json={"camera": CAMERA, "points": None}).status_code == expected, status
            assert client.get("/snapshot?camera=" + CAMERA).status_code == expected, status
        answer["status"] = 401
        signed_out = client.get("/")
        assert signed_out.status_code == 302 and signed_out.headers["Location"] == "/auth/sign-in"
    api.shutdown()
    api.server_close()
    with mock.patch.object(app, "ROI_AUTH_URL", f"http://127.0.0.1:{api.server_port}/auth/check-admin"):
        assert app.app.test_client().get("/api/cameras").status_code == 503, "no API: refused"
    print("roi gate ok (every request but /health asks the API, own method sent, 401 403 and unavailable refused before any camera)")


def test_concurrent_saves():
    """Saves for two cameras at once both survive, and each is logged with the admin who made it."""
    folder = tempfile.mkdtemp()
    config = os.path.join(folder, "camera_configuration.json")
    with open(config, "w") as f:
        json.dump(SAMPLE, f)
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)
    square = [[100, 100], [500, 100], [500, 400], [100, 400]]
    lines = []
    handler = logging.Handler()
    handler.emit = lambda record: lines.append(record.getMessage())
    app.audit.addHandler(handler)
    real_load = app.load_config

    def slow_load():
        data = real_load()
        threading.Event().wait(0.2)  # long enough for the other save to read the same old file without the lock
        return data

    with mock.patch.object(app, "CAMERA_CONFIGURATION_FILE", config), mock.patch.object(app, "snapshot", lambda camera: frame),             mock.patch.object(app, "check_admin", lambda: (204, "boss")), mock.patch.object(app, "load_config", slow_load):
        def save(camera):
            assert app.app.test_client().post("/api/roi", json={"camera": camera, "points": square, "size": [1280, 720]}).status_code == 200
        workers = [threading.Thread(target=save, args=(c,)) for c in (CAMERA, "maingate/entry/cctv-camera-2")]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
    entry = json.load(open(config))["maingate"]["cctv-cameras"]["entry"]
    assert entry["cctv-camera-1"]["masking-coordinates"] == square and entry["cctv-camera-2"]["masking-coordinates"] == square
    assert sorted(lines) == sorted(f"region saved for {c} by boss, 4 points on 1280x720" for c in (CAMERA, "maingate/entry/cctv-camera-2")), lines
    app.audit.removeHandler(handler)
    shutil.rmtree(folder)
    print("roi saves ok (two cameras at once both kept, each logged with its admin)")


if __name__ == "__main__":
    test()
    test_gate()
    test_concurrent_saves()
