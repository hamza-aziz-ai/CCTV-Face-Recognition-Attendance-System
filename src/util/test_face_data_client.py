"""The face crop sender reports what the collector kept: 207 and errors are failures, an edge token never goes over plain
HTTP, and a slow collector makes it drop batches instead of queueing them without end.
Run in the producer-consumer image: python3 src/util/test_face_data_client.py"""
import http.server
import os
import sys
import threading
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import util.face_data_client as client  # noqa: E402

CROPS = {"p1": [(np.zeros((8, 8, 3), np.uint8), 0.9, "maingate_entry_cctv-camera-1", [(0, 0), (60, 0)])]}
answers = []


class Collector(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        status, body = answers.pop(0)
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    answers.extend([(200, b"{}"), (207, b'{"failures": [{"index": 0}]}'), (500, b"{}")])
    assert client.send_faces_via_api(CROPS, url) is True
    assert client.send_faces_via_api(CROPS, url) is False, "207 passed raise_for_status and counted as sent"
    assert client.send_faces_via_api(CROPS, url) is False
    server.shutdown()
    server.server_close()
    assert client.send_faces_via_api(CROPS, url) is False

    with mock.patch.object(client, "DYNAMIC_FACE_DATA_COLLECTOR_TOKEN", "secret"), mock.patch.object(client.requests, "post") as post:
        assert client.send_faces_via_api(CROPS, "http://central/api/v1/edge") is False
        assert not post.called, "the token went over plain HTTP"
        post.return_value.status_code = 200
        assert client.send_faces_via_api(CROPS, "https://central/api/v1/edge") is True
        assert post.call_args.args[0] == "https://central/api/v1/edge/faces"
        assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"} and "verify" not in post.call_args.kwargs

    release = threading.Event()
    with mock.patch.object(client, "send_faces_via_api", lambda *a: release.wait(10)):
        assert all(client.submit_faces_async(CROPS, url) for _ in range(32))
        assert client.submit_faces_async(CROPS, url) is False and client.dropped == 1
        release.set()
        client._executor.submit(lambda: None).result()
        for _ in range(100):
            if client.submit_faces_async(CROPS, url):
                break
            threading.Event().wait(0.05)
        else:
            raise AssertionError("slots never came back")
    print("face crop sender ok (200 sent, 207, 500 and no collector failed, token only over https, 33rd waiting batch dropped and slots returned)")


if __name__ == "__main__":
    test()
