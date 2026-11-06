"""Delivers recognition batches to the database controller's /ingest and retries them until they are saved, across restarts.

Every batch is first written to the spool folder on disk and flushed (fsync) before it is queued, and its file is deleted
only once the controller confirms the batch is saved. On start the sender reloads whatever the spool holds, oldest first,
so a restart, a crash or a power cut loses no recognised attendance. In the stack the spool is the client's own Docker
volume (docker-compose-main.yml, attendance-spool): a named volume because fsync is unreliable on Windows folder mounts
(D-038), per client because compose prefixes it with the project, and removed with the client (deploy/recovery.py).

One sender per producer-consumer process does every send, oldest first, so a new batch never overtakes one that failed,
and recognition never waits on the database. A batch is sent again unchanged: the controller skips a record it already
has by the record's own time, so a batch whose answer was lost is never saved twice. A batch counts as saved only when the
controller answers 200 with "committed": true; a plain 200 comes from an older controller that answered before writing.
A 4xx means the payload can never be saved: its file moves to the spool's rejected/ folder, kept for someone to look at,
and it is not retried, so it cannot block the queue. Anything else (no connection, timeout, 5xx) is retried every
RETRY_SECONDS.

The spool is bounded in bytes: when full, or when a batch cannot be written to disk, new batches are refused and counted
as lost, never the waiting ones; both keep readiness down. Frames still waiting to be recognised when the process stops
are not covered: they are video, not yet attendance.

Run the self-check: python3 src/util/attendance_sender.py
"""
import collections
import json
import os
import sys
import threading
import time
from pathlib import Path

current = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [os.path.dirname(current)]
from custom_logging import database_server_logger as logger  # noqa: E402

BUDGET_BYTES = 2 * 2 ** 30  # provisional: every detected face carries a full frame, about 10,000 records
RETRY_SECONDS = 2.0
TIMEOUT_SECONDS = 30  # above the controller's 20 s transaction deadline, so a slow batch fails there first
LOSS_HOLD_SECONDS = 600  # a loss or a rejection keeps readiness down this long, and stays in the counts


def durable_write(path, data):
    """Writes a file so it survives a crash: a temporary name, flushed to disk, then renamed and the folder flushed."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    if hasattr(os, "O_DIRECTORY"):  # POSIX: the rename itself must reach the disk
        folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)


class AttendanceSender:
    def __init__(self, post, spool, budget=BUDGET_BYTES, retry_seconds=RETRY_SECONDS, clock=time.monotonic):
        self.post = post  # post(body bytes) -> (status code, parsed JSON or None); raises on no answer
        self.spool = Path(spool)
        self.rejected = self.spool / "rejected"
        self.rejected.mkdir(parents=True, exist_ok=True)
        self.budget, self.retry_seconds, self.clock = budget, retry_seconds, clock
        self.changed = threading.Condition()
        self.failing = False  # the batch at the head failed or was not confirmed, and is waiting to be sent again
        self.sending_since = None
        self.lost_batches = self.lost_records = self.rejected_batches = 0
        self.last_loss = None
        self.stopping = False
        for tmp in self.spool.glob("*.tmp"):  # a write cut short by a crash: never queued, so never acknowledged
            tmp.unlink()
        # File names are <sequence>-<records>.json: sorting them is the order they were recognised in
        self.pending = collections.deque(sorted(self.spool.glob("*.json")))
        self.bytes = sum(path.stat().st_size for path in self.pending)
        self.sequence = max((int(path.name.split("-")[0]) for path in self.pending), default=0)
        if self.pending:
            logger.warning(f"Attendance spool: {len(self.pending)} batch(es) from before the restart, sending them first")

    def submit(self, payload, records):
        """Writes one batch to the spool and queues it; False when it cannot be kept (counted as lost)."""
        body = json.dumps(payload).encode()
        with self.changed:
            if self.bytes + len(body) > self.budget:
                self.lose(1, records, "the spool is full")
                return False
            self.sequence = max(self.sequence + 1, time.time_ns())
            path = self.spool / f"{self.sequence:020d}-{records}.json"
            try:
                durable_write(path, body)
            except OSError as error:
                self.lose(1, records, f"the spool cannot be written ({type(error).__name__})")
                return False
            self.pending.append(path)
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
        """Sends the oldest batch once. True when it is done with (saved, or rejected and set aside)."""
        with self.changed:
            path = self.pending[0]
        body = path.read_bytes()
        self.sending_since = self.clock()
        try:
            status, answer = self.post(body)
        except Exception as error:
            status, answer = type(error).__name__, None
        finally:
            self.sending_since = None
        saved = status == 200 and isinstance(answer, dict) and answer.get("committed") is True
        refused = isinstance(status, int) and 400 <= status < 500
        if not saved and not refused:
            if not self.failing:
                logger.error(f"Attendance batch not confirmed ({status}); retrying every {self.retry_seconds:g} s")
            self.failing = True
            return False
        if saved:
            path.unlink()
        else:
            os.replace(path, self.rejected / path.name)
            self.rejected_batches += 1
            self.last_loss = self.clock()
            logger.error(f"Attendance batch {path.name} refused by the controller ({status}); kept in {self.rejected}")
        with self.changed:
            self.pending.popleft()
            self.bytes -= len(body)
        self.failing = False
        return True

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
        """On a graceful stop: tries to send what is waiting; what is left stays in the spool for the next start."""
        with self.changed:
            self.stopping = True
            self.changed.notify()
        deadline = self.clock() + wait_seconds
        while self.pending and self.clock() < deadline:
            time.sleep(0.1)
        if self.pending:
            logger.warning(f"Attendance spool: {len(self.pending)} batch(es) kept for the next start")

    def state(self):
        """(ready, reason). Batches simply waiting their turn are normal work; a failed or unconfirmed send, a send
        stuck past its timeout, or a recent loss or rejection is not."""
        now = self.clock()
        if self.failing:
            return False, "attendance_write_failing"
        if self.sending_since is not None and now - self.sending_since > TIMEOUT_SECONDS + 5:
            return False, "attendance_sender_stalled"
        if self.last_loss is not None and now - self.last_loss < LOSS_HOLD_SECONDS:
            return False, "attendance_records_lost" if self.lost_batches else "attendance_records_rejected"
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
    import tempfile

    answers, sent = [], []

    def post(body):
        sent.append(body)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    now = [0.0]
    batch = {"current_date": "2026-11-06", "current_time": "10:00:00", "results": {"p": [["cam", "ip", 0.9, "x", [1, 2, 3, 4]]]}}
    with tempfile.TemporaryDirectory() as spool:
        sender = AttendanceSender(post, spool, budget=250, retry_seconds=0, clock=lambda: now[0])
        assert sender.submit(batch, 1) and sender.submit(dict(batch, current_time="10:00:01"), 2)
        assert len(list(Path(spool).glob("*.json"))) == 2, "every batch is on disk before it is queued"
        assert sender.state() == (True, None), "batches waiting their turn are normal work"

        # A restart, even a crash mid-write, loses nothing: the spool is reloaded oldest first, half-written files dropped
        (Path(spool) / "00000000000000000001-1.tmp").write_bytes(b"{")
        sender = AttendanceSender(post, spool, budget=250, retry_seconds=0, clock=lambda: now[0])
        assert [p.name.split("-")[1] for p in sender.pending] == ["1.json", "2.json"] and not list(Path(spool).glob("*.tmp"))

        # A failed or unconfirmed send keeps the batch, unchanged, on disk and at the head, and readiness down
        answers += [ConnectionError("down"), (503, None), (200, {"status": "OK"}), (200, {"status": "OK", "committed": True})]
        for _ in range(3):
            assert not sender.send_head()
            assert sender.state() == (False, "attendance_write_failing")
        assert sender.send_head() and len(set(sent)) == 1, "a retry must send the same bytes"
        assert sender.state() == (True, None) and len(sender.pending) == 1 and len(list(Path(spool).glob("*.json"))) == 1

        # A refused payload is set aside in rejected/, not deleted, and holds readiness down for a while
        answers.append((400, {"detail": "bad"}))
        assert sender.send_head() and not sender.pending and len(list(sender.rejected.glob("*.json"))) == 1
        assert sender.state() == (False, "attendance_records_rejected")
        now[0] += LOSS_HOLD_SECONDS
        assert sender.state() == (True, None) and sender.rejected_batches == 1

        # The budget counts bytes on disk: a batch that does not fit is refused and the waiting ones are kept
        big = dict(batch, results={"p": [["cam", "ip", 0.9, "y" * 150, [1, 2, 3, 4]]]})
        assert sender.submit(batch, 1) and not sender.submit(big, 3)
        assert len(sender.pending) == 1 and sender.lost_records == 3 and sender.state() == (False, "attendance_records_lost")

        # A spool that cannot be written refuses the batch and says so
        sender.spool = Path(spool) / "missing"
        assert not sender.submit(batch, 1) and sender.lost_batches == 2
        sender.spool = Path(spool)

        # A send stuck past its timeout is not normal work either
        sender.last_loss = None
        sender.sending_since = now[0] - TIMEOUT_SECONDS - 6
        assert sender.state() == (False, "attendance_sender_stalled")
    print("attendance sender ok (written to disk before queueing, reloaded oldest first after a restart, unchanged retries, "
          "unconfirmed 200 retried, refused payload kept aside, byte budget, unwritable spool, stall)")


if __name__ == "__main__":
    demo()
