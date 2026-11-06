"""Whether producer-consumer is really working, for Docker's healthcheck and the display (GET /health on
PIPELINE_HEALTH_PORT): starting, ready or unready, with reason codes only, never IDs, names, images or credentials.

Workers write their own progress: each camera thread on every frame it handles and on every reconnect attempt, each
recognition thread on every pass while waiting and after every batch, with the batch's outcome. Nothing else writes it, so
a worker that hangs stops renewing it. Waiting is healthy: a dark camera or an empty queue keeps its worker's progress fresh.
A camera that cannot be reached is retried by its thread, which marks itself retrying: it counts as started but is not
held to the deadline, since opening an unreachable stream can take minutes when many are retried, and the camera is
reported on its own by its ERROR on the display. # ponytail: a thread that hangs while opening a stream goes unnoticed
here; bound the open (util/video_source.py) and drop this exemption if that turns up. A worker silent past its deadline, recognition failing several batches in a row, the attendance
sender failing (util/attendance_sender.py) or a dependency check failing makes it unready. Dependency checks run in the
background with a deadline each and count only while recent, so an old success never hides a new failure.

The progress lives in shared memory created before the producer process forks, one slot per worker, each written by one
worker only. Hung workers are reported, not restarted: restarts come only from a worker dying (src/main.py), until the
deadlines are measured on real cameras.

Run the self-check: python3 src/util/pipeline_health.py
"""
import json
import multiprocessing
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

current = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [os.path.dirname(current)]

CAMERA_DEADLINE = 90  # seconds without progress: above a 30 s reconnect wait plus opening the stream
RECOGNITION_DEADLINE = 180  # above InsightFace's 120 s request timeout, so a slow batch is not a hang
FAILED_BATCHES = 3  # recognition batches failing in a row
CHECK_SECONDS = 15
CHECK_DEADLINE = 10
CHECK_MAX_AGE = 45
STARTING_SECONDS = 300  # until every worker has made progress once and every check has passed once, within this


class Workers:
    """Progress slots shared across the producer's fork: one per camera thread and recognition thread."""

    def __init__(self, cameras, recognizers, clock=time.monotonic):
        self.names = [f"camera:{name}" for name in cameras] + [f"recognition:{name}" for name in recognizers]
        self.clock = clock
        self.seen = multiprocessing.Array("d", len(self.names), lock=False)  # 0: never
        self.failures = multiprocessing.Array("i", len(self.names), lock=False)
        self.retrying = multiprocessing.Array("b", len(self.names), lock=False)

    def slot(self, kind, name):
        return self.names.index(f"{kind}:{name}")

    def beat(self, kind, name, retrying=False):
        index = self.slot(kind, name)
        self.retrying[index] = retrying
        self.seen[index] = self.clock()

    def batch(self, name, ok):
        index = self.slot("recognition", name)
        self.failures[index] = 0 if ok else self.failures[index] + 1
        self.seen[index] = self.clock()

    def problems(self, now):
        """(starting, reasons)."""
        reasons, starting = set(), False
        for index, name in enumerate(self.names):
            kind = name.split(":")[0]
            if not self.seen[index]:
                starting = True
            elif not self.retrying[index] and now - self.seen[index] > (CAMERA_DEADLINE if kind == "camera" else RECOGNITION_DEADLINE):
                reasons.add(f"{kind}_stalled")
            if self.failures[index] >= FAILED_BATCHES:
                reasons.add("recognition_failing")
        return starting, reasons


class Checks:
    """Dependency checks run in the background; only the latest result of each counts, and only while recent."""

    def __init__(self, checks, clock=time.monotonic):
        self.checks = checks  # {name: callable that raises on failure}
        self.clock = clock
        self.results = {name: {"started": None, "passed_at": None, "failed": False} for name in checks}

    def run_once(self, name):
        result = self.results[name]
        result["started"] = self.clock()
        try:
            self.checks[name]()
            result.update(passed_at=self.clock(), failed=False)
        except Exception:
            result["failed"] = True
        result["started"] = None

    def loop(self, name):
        while True:
            self.run_once(name)
            time.sleep(CHECK_SECONDS)

    def start(self):
        for name in self.checks:
            threading.Thread(target=self.loop, args=(name,), name=f"check-{name}", daemon=True).start()
        return self

    def problems(self, now):
        reasons, starting = set(), False
        for name, result in self.results.items():
            if result["passed_at"] is None and not result["failed"]:
                starting = True
            elif (result["failed"] or (result["started"] is not None and now - result["started"] > CHECK_DEADLINE)
                  or now - (result["passed_at"] or float("-inf")) > CHECK_MAX_AGE):
                reasons.add(f"{name}_unavailable")
        return starting, reasons


def readiness(workers, checks, sender_state, started_at, now):
    """(status, reasons) with status starting, ready or unready."""
    worker_starting, reasons = workers.problems(now)
    check_starting, check_reasons = checks.problems(now)
    reasons |= check_reasons
    ready, reason = sender_state()
    if not ready:
        reasons.add(reason)
    if reasons:
        return "unready", sorted(reasons)
    if worker_starting or check_starting:
        return ("starting", []) if now - started_at < STARTING_SECONDS else ("unready", ["not_started"])
    return "ready", []


def serve(port, status):
    """GET /health: 200 when ready, 503 otherwise, with {"status": ..., "reasons": [...]}."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health":
                self.send_error(404)
                return
            state, reasons = status()
            body = json.dumps({"status": state, "reasons": reasons}).encode()
            self.send_response(200 if state == "ready" else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # every probe would fill the log
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="health", daemon=True).start()
    return server


def demo():
    now = [1000.0]
    clock = lambda: now[0]  # noqa: E731
    workers = Workers(["maingate_entry_cctv-camera-1"], ["thread_0"], clock)
    checks = Checks({"insightface": lambda: None, "database": lambda: (_ for _ in ()).throw(ConnectionError())}, clock)
    sender = [(True, None)]
    state = lambda: readiness(workers, checks, lambda: sender[0], 1000.0, now[0])  # noqa: E731

    assert state() == ("starting", []), state()
    workers.beat("camera", "maingate_entry_cctv-camera-1")
    workers.batch("thread_0", ok=True)
    checks.run_once("insightface")
    assert state() == ("starting", []), "a check that has not answered yet is still starting"
    checks.run_once("database")
    assert state() == ("unready", ["database_unavailable"]), state()
    checks.checks["database"] = lambda: None
    checks.run_once("database")
    assert state() == ("ready", []), state()

    # Waiting is healthy as long as the worker keeps renewing its progress; silence past the deadline is not
    now[0] += 60
    workers.batch("thread_0", ok=True)
    checks.run_once("insightface"), checks.run_once("database")
    assert state() == ("ready", [])
    now[0] += 31
    checks.run_once("insightface"), checks.run_once("database")
    assert state() == ("unready", ["camera_stalled"]), state()
    workers.beat("camera", "maingate_entry_cctv-camera-1", retrying=True)
    now[0] += 600
    checks.run_once("insightface"), checks.run_once("database")
    workers.batch("thread_0", ok=True)
    assert state() == ("ready", []), "a camera being retried is not held to the deadline"
    workers.beat("camera", "maingate_entry_cctv-camera-1")

    # Batches failing in a row, and an old check success, do not count as working
    for _ in range(FAILED_BATCHES):
        workers.batch("thread_0", ok=False)
    assert state() == ("unready", ["recognition_failing"]), state()
    workers.batch("thread_0", ok=True)
    now[0] += CHECK_MAX_AGE + 1
    assert state() == ("unready", ["database_unavailable", "insightface_unavailable"]), state()
    checks.run_once("insightface"), checks.run_once("database")
    checks.results["database"]["started"] = now[0] - CHECK_DEADLINE - 1
    assert state() == ("unready", ["database_unavailable"]), "a check running past its deadline counts as failing"
    checks.results["database"]["started"] = None

    # The attendance sender's state counts too
    sender[0] = (False, "attendance_write_failing")
    assert state() == ("unready", ["attendance_write_failing"])
    sender[0] = (True, None)

    # A worker that never makes progress at all ends the start-up grace
    late = Workers(["maingate_entry_cctv-camera-1"], ["thread_0"], clock)
    late.beat("camera", "maingate_entry_cctv-camera-1")
    assert readiness(late, checks, lambda: (True, None), now[0] - STARTING_SECONDS, now[0]) == ("unready", ["not_started"])

    # Over HTTP
    import urllib.request
    import urllib.error
    server = serve(0, state)
    url = f"http://127.0.0.1:{server.server_address[1]}/health"
    assert json.load(urllib.request.urlopen(url)) == {"status": "ready", "reasons": []}
    sender[0] = (False, "attendance_records_lost")
    try:
        urllib.request.urlopen(url)
        raise AssertionError("unready must answer 503")
    except urllib.error.HTTPError as error:
        assert error.code == 503 and json.load(error) == {"status": "unready", "reasons": ["attendance_records_lost"]}
    server.shutdown()
    print("pipeline health ok (starting, ready, stalled worker, failing batches, expired and overrunning checks, "
          "attendance sender, start-up grace, HTTP 200/503)")


if __name__ == "__main__":
    demo()
