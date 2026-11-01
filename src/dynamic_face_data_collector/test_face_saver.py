"""save_face_if_better keeps a full cluster when the new crop is worse, and swaps out the worst crop when it is better.
Run in the dynamic-face-dataset-collector image: python3 src/dynamic_face_data_collector/test_face_saver.py"""
import json
import os
import sys
import tempfile
import threading
import types
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
# No database here: the crop records are not what this checks
sys.modules["postgresql_database_handler"] = types.SimpleNamespace(insert_face_data=lambda *a: None,
                                                                   delete_face_data=lambda *a: None)
import face_saver  # noqa: E402


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


if __name__ == "__main__":
    test()
