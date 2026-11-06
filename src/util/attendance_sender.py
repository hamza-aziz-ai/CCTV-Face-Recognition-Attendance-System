"""Delivers recognition batches to the database controller's /ingest and retries them until they are saved.

One sender per producer-consumer process does every send, oldest first, so a new batch never overtakes one that failed,
and recognition never waits on the database. A batch is serialized once and sent again unchanged: the controller skips a
record it already has by the record's own time, so a batch whose answer was lost is never saved twice. A batch counts as
saved only when the controller answers 200 with "committed": true; a plain 200 comes from an older controller that answered
before writing. A 4xx means the payload can never be saved: it is logged, counted as lost, and not retried, so it cannot
block the queue. Anything else (no connection, timeout, 5xx) is retried every RETRY_SECONDS.

The queue lives in memory, bounded in bytes including the batch being sent: when full, new batches are refused and
counted as lost, never the waiting ones. Batches still waiting are lost on an abrupt restart (stop() sends what it can
first). # ponytail: memory queue, a queue on disk if outages turn out longer than the budget holds.

Run the self-check: python3 src/util/attendance_sender.py
"""
import collections
import json
import os
import sys
import threading
import time

current = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [os.path.dirname(current)]
from custom_logging import database_server_logger as logger  # noqa: E402

BUDGET_BYTES = 64 * 2 ** 20  # provisional: every detected face carries a full frame, measure before relying on it
RETRY_SECONDS = 2.0
TIMEOUT_SECONDS = 30  # above the controller's 20 s transaction deadline, so a slow batch fails there first
LOSS_HOLD_SECONDS = 600  # a loss keeps readiness down this long, and stays in the counts


class AttendanceSender:
    def __init__(self, post, budget=BUDGET_BYTES, retry_seconds=RETRY_SECONDS, clock=time.monotonic):
        self.post = post  # post(body bytes) -> (status code, parsed JSON or None); raises on no answer
        self.budget, self.retry_seconds, self.clock = budget, retry_seconds, clock
        self.pending = collections.deque()
        self.bytes = 0
        self.changed = threading.Condition()
        self.failing = False  # the batch at the head failed or was not confirmed, and is waiting to be sent again
        self.sending_since = None
        self.lost_batches = self.lost_records = 0
        self.last_loss = None
        self.stopping = False

    def submit(self, payload, records):
        """Queues one batch; False when the budget is full and the batch is refused (counted as lost)."""
        body = json.dumps(payload).encode()
        with self.changed:
            if self.bytes + len(body) > self.budget:
                self.lose(1, records, "queue full")
                return False
            self.pending.append((body, records))
            self.bytes += len(body)
            self.changed.notify()
        return True

    def lose(self, batches, records, why):
        self.lost_batches += batches
        self.lost_records += records
        self.last_loss = self.clock()
        logger.error(f"Attendance not saved: {batches} batch(es), {records} record(s) lost ({why}); "
                     f"{self.lost_batches} batch(es) lost since start")

    def send_head(self):
        """Sends the oldest batch once. True when it is done with (saved or refused for good)."""
        with self.changed:
            body, records = self.pending[0]
        self.sending_since = self.clock()
        try:
            status, answer = self.post(body)
        except Exception as error:
            status, answer = type(error).__name__, None
        finally:
            self.sending_since = None
        saved = status == 200 and isinstance(answer, dict) and answer.get("committed") is True
        refused = isinstance(status, int) and 400 <= status < 500
        if saved or refused:
            with self.changed:
                self.pending.popleft()
                self.bytes -= len(body)
            if refused:
                self.lose(1, records, f"the controller refused the payload with {status}")
            self.failing = False
            return True
        if not self.failing:
            logger.error(f"Attendance batch not confirmed ({status}); retrying every {self.retry_seconds:g} s")
        self.failing = True
        return False

    def run(self):
        while True:
            with self.changed:
                while not self.pending and not self.stopping:
                    self.changed.wait()
                if self.stopping and not self.pending:
                    return
            if not self.send_head():
                if self.stopping:
                    return
                time.sleep(self.retry_seconds)

    def start(self):
        threading.Thread(target=self.run, name="attendance-sender", daemon=True).start()
        return self

    def stop(self, wait_seconds=10):
        """On a graceful stop: tries to send what is waiting, then reports what could not be."""
        with self.changed:
            self.stopping = True
            self.changed.notify()
        deadline = self.clock() + wait_seconds
        while self.pending and self.clock() < deadline:
            time.sleep(0.1)
        if self.pending:
            self.lose(len(self.pending), sum(records for _, records in self.pending), "stopped before they could be sent")

    def state(self):
        """(ready, reason). Batches simply waiting their turn are normal work; a failed or unconfirmed send, a send
        stuck past its timeout, or a recent loss is not."""
        now = self.clock()
        if self.failing:
            return False, "attendance_write_failing"
        if self.sending_since is not None and now - self.sending_since > TIMEOUT_SECONDS + 5:
            return False, "attendance_sender_stalled"
        if self.last_loss is not None and now - self.last_loss < LOSS_HOLD_SECONDS:
            return False, "attendance_records_lost"
        return True, None


def http_post(url):
    import requests

    session = requests.Session()

    def post(body):
        response = session.post(url, data=body, headers={"Content-Type": "application/json"}, timeout=TIMEOUT_SECONDS)
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, None

    return post


def demo():
    answers = []
    sent = []

    def post(body):
        sent.append(body)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    now = [0.0]
    sender = AttendanceSender(post, budget=250, retry_seconds=0, clock=lambda: now[0])
    batch = {"current_date": "2026-11-06", "current_time": "10:00:00", "results": {"p": [["cam", "ip", 0.9, "x", [1, 2, 3, 4]]]}}
    assert sender.submit(batch, 1) and sender.submit(dict(batch, current_time="10:00:01"), 1)
    assert sender.state() == (True, None), "batches waiting their turn are normal work"

    # A failed send keeps the batch at the head, unchanged, and readiness down until it is confirmed
    answers += [ConnectionError("down"), (503, None), (200, {"status": "OK"}), (200, {"status": "OK", "committed": True})]
    for _ in range(3):
        assert not sender.send_head()
        assert sender.state() == (False, "attendance_write_failing")
    assert sender.send_head() and len(set(sent)) == 1, "a retry must send the same bytes"
    assert sender.state() == (True, None) and len(sender.pending) == 1

    # A refused payload is dropped for good, counted, and holds readiness down for a while
    answers.append((400, {"detail": "bad"}))
    assert sender.send_head() and not sender.pending and sender.lost_records == 1
    assert sender.state() == (False, "attendance_records_lost")
    now[0] += LOSS_HOLD_SECONDS
    assert sender.state() == (True, None) and sender.lost_batches == 1, "the loss stays counted"

    # The budget counts bytes: a batch that does not fit is refused and the waiting ones are kept
    big = dict(batch, results={"p": [["cam", "ip", 0.9, "y" * 150, [1, 2, 3, 4]]]})
    assert sender.submit(batch, 1) and not sender.submit(big, 3)
    assert len(sender.pending) == 1 and sender.lost_records == 4

    # A send stuck past its timeout is not normal work either
    sender.sending_since = now[0]
    now[0] += TIMEOUT_SECONDS + 6
    assert sender.state()[1] in ("attendance_sender_stalled", "attendance_records_lost")
    sender.sending_since, sender.last_loss = now[0] - TIMEOUT_SECONDS - 6, None
    assert sender.state() == (False, "attendance_sender_stalled")
    print("attendance sender ok (unchanged retries, unconfirmed 200 retried, refused payload dropped and counted, "
          "byte budget, loss and stall keep readiness down)")


if __name__ == "__main__":
    demo()
