"""save_face_if_better keeps a full cluster when the new crop is worse, and swaps out the worst crop when it is better.
Each camera's cluster comes from the camera configuration: its "cluster" key, else its own name; a camera that is not
configured, or a cluster that is not a plain folder name, is refused. A crop that could not be stored is reported to the
caller (207) and leaves no file behind; a record that could reach outside its folder is refused before any file is touched.
Run in the dynamic-face-dataset-collector image: python3 src/dynamic_face_data_collector/test_face_saver.py"""
import json
import os
import sys
import tempfile
import threading
import types
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
# The collector reads the camera configuration when imported, and images hold none
CAMERAS = {"maingate": {"api-endpoint": "", "cctv-cameras": {
    "entry": {"cctv-camera-1": {"cluster": "cluster-1"}, "cctv-camera-2": {"cluster": "cluster-1"}, "cctv-camera-11": {}},
    "exit": None}}, "library": {"api-endpoint": "", "cctv-cameras": {"entry": {"cctv-camera-1": {"masking-coordinates": None}}}}}
os.chdir(tempfile.mkdtemp())
os.makedirs("src/Camera-Configuration")
with open("src/Camera-Configuration/camera_configuration.json", "w") as f:
    json.dump(CAMERAS, f)
# No database here: the crop records are not what this checks
sys.modules["postgresql_database_handler"] = types.SimpleNamespace(insert_face_data=lambda *a: None,
                                                                   delete_face_data=lambda *a: None,
                                                                   initialize_database_and_tables=lambda: None)
import face_saver  # noqa: E402
import api  # noqa: E402


def test_clusters():
    from util.generic_utilities import camera_clusters
    assert face_saver.get_cluster("maingate_entry_cctv-camera-1") == face_saver.get_cluster("maingate_entry_cctv-camera-2") == "cluster-1"
    assert face_saver.get_cluster("maingate_entry_cctv-camera-11") == "maingate_entry_cctv-camera-11", "used to raise: not in the old fixed map"
    assert face_saver.get_cluster("library_entry_cctv-camera-1") == "library_entry_cctv-camera-1"
    try:
        face_saver.get_cluster("maingate_entry_cctv-camera-99")
        raise AssertionError("a camera that is not configured must be refused")
    except KeyError:
        pass
    for bad in ("../x", "a/b", ".hidden", "x" * 101, 7):  # an empty or missing key means the camera's own name
        try:
            camera_clusters({"m": {"cctv-cameras": {"e": {"c": {"cluster": bad}}}}})
            raise AssertionError(f"cluster {bad!r} accepted")
        except ValueError:
            pass
    print("clusters ok (explicit key pools cameras, any other camera is its own cluster, unknown cameras and unsafe names refused)")


def test():
    folder = tempfile.mkdtemp()
    crop = np.zeros((8, 8, 3), np.uint8)
    with mock.patch.object(face_saver, "DYNAMIC_DATASET_PATH", folder), \
            mock.patch.object(face_saver, "get_cluster", lambda camera: "cluster-1"):
        cluster = os.path.join(folder, "p1", "cluster-1")

        def kept():
            with open(os.path.join(cluster, "meta.json")) as f:
                return sorted(entry["pupil_distance"] for entry in json.load(f))

        for pupils in (40, 50, 60):
            face_saver.save_face_if_better("p1", "cam", crop, pupils, 0.9)
        assert kept() == [40, 50, 60], kept()

        # A worse crop on a full cluster used to loop forever inside the request
        worker = threading.Thread(target=face_saver.save_face_if_better, args=("p1", "cam", crop, 30, 0.9), daemon=True)
        worker.start()
        worker.join(10)
        assert not worker.is_alive(), "a worse crop on a full cluster never returned"
        assert kept() == [40, 50, 60], kept()

        face_saver.save_face_if_better("p1", "cam", crop, 70, 0.9)
        assert kept() == [50, 60, 70], kept()
        assert len([name for name in os.listdir(cluster) if name.endswith(".jpg")]) == 3
    print("face saver ok (full cluster kept against a worse crop, worst crop replaced by a better one)")


def test_failures():
    import asyncio
    import base64
    import cv2
    from pydantic import ValidationError
    folder = tempfile.mkdtemp()
    image = base64.b64encode(cv2.imencode(".jpg", np.zeros((8, 8, 3), np.uint8))[1].tobytes()).decode()
    good = dict(person_id="p1", camera_name="maingate_entry_cctv-camera-1", match_score=0.9, landmarks=[(0, 0), (60, 0)], image_base64=image)
    for bad in ({"person_id": "../x"}, {"person_id": "a/b"}, {"person_id": ""}, {"match_score": float("nan")}, {"landmarks": [(0, 0)]}):
        try:
            api.FaceRecord(**{**good, **bad})
            raise AssertionError(f"accepted {bad}")
        except ValidationError:
            pass

    def broken(*args):
        raise RuntimeError("database down")
    with mock.patch.object(face_saver, "DYNAMIC_DATASET_PATH", folder), mock.patch.object(face_saver, "insert_face_data", broken):
        records = [api.FaceRecord(**good), api.FaceRecord(**{**good, "camera_name": "maingate_entry_cctv-camera-99"})]
        answer = asyncio.run(api.submit_faces(records))
        failures = json.loads(answer.body)["failures"]
        assert answer.status_code == 207 and [f["index"] for f in failures] == [0, 1], answer.body  # used to be 200: the error was only logged
        assert "database down" in failures[0]["error"] and "Unknown camera" in failures[1]["error"], failures
        kept = os.path.join(folder, "p1", "cluster-1")
        assert not [name for name in os.listdir(kept) if name.endswith(".jpg")], "a crop with no row must not stay on disk"
    with mock.patch.object(face_saver, "DYNAMIC_DATASET_PATH", folder):
        answer = asyncio.run(api.submit_faces([api.FaceRecord(**good)]))
        assert answer.status_code == 200, answer.body
    print("failures ok (unsafe person ID, bad score and too few landmarks refused; storage failure and unknown camera reported as 207, no file left)")


if __name__ == "__main__":
    test_clusters()
    test_failures()
    test()
