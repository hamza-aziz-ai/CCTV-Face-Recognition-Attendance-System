"""Enrolment API (8c, D-048), the server side of the enrolment app's contract (Face-Dataset-Collector FEATURE-001).
Reached as /api/v1/... through the proxy, which strips /api. The tenant is this stack's client (D-036): no request names
one. Uploads go to this client's MinIO bucket and a job row; the enrolment worker checks and publishes them. Run in the
API container to manage the roster:
  python3 src/api/enrolment.py add-person PERSON_ID "NAME" [EMPLOYEE_CODE] [DEPARTMENT]
  python3 src/api/enrolment.py import-persons FILE.csv     columns: person_id,name,employee_code,department
"""
import csv
import re
import email.parser
import email.policy
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Callable, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

current = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [os.path.dirname(current), os.path.join(os.path.dirname(current), "util")]
import accounts  # noqa: E402
from custom_logging import api_logger  # noqa: E402
from enrolment_checks import GLASSES, POSES  # noqa: E402
from parameters import CLIENT_ID, CLIENT_NAME, ENROLMENT_MAX_BODY_BYTES, ENROLMENT_MAX_PHOTO_BYTES, \
    ENROLMENT_NOTICE_FILE  # noqa: E402

ENROL_ROLES = ("client_admin", "enrolment_operator")
REASONS = ("appearance_changed", "poor_photos", "other")
CONSENT_METHOD = "staff_attested_in_app"

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    employee_code TEXT,
    department TEXT,
    enrolled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS consents (
    id UUID PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES persons,
    notice_version TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    method TEXT NOT NULL,
    recorded_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    withdrawn_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS enrolment_jobs (
    id UUID PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES persons,
    consent_id UUID NOT NULL REFERENCES consents,
    reason TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    body_hash TEXT NOT NULL,
    poses TEXT[] NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    problems JSONB NOT NULL DEFAULT '[]',
    submitted_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS enrolment_jobs_one_open ON enrolment_jobs (person_id) WHERE status = 'pending';
-- "AB12" and "ab12" would share a folder on Windows and macOS, so they are one person
CREATE UNIQUE INDEX IF NOT EXISTS persons_id_any_case ON persons (lower(person_id));
"""

router = APIRouter(prefix="/v1")
cursor_source: Optional[Callable] = None
store = None  # enrolment_store.Store, or a MemoryStore in tests


def setup(get_cursor: Callable, photo_store=None):
    global cursor_source, store
    cursor_source = get_cursor
    with get_cursor(commit=True) as cursor:
        cursor.execute(SCHEMA)
    if photo_store is None:
        from enrolment_store import Store
        photo_store = Store()
    store = photo_store


def error(status: int, code: str, **extra) -> JSONResponse:
    """Errors as {"error": code}, the codes the enrolment app maps to messages."""
    return JSONResponse({"error": code, **extra}, status_code=status)


def enroller(request: Request) -> dict:
    """Signed in with a role that may enrol: 401 means signed out, 403 role_cannot_enrol, which the app shows apart."""
    caller = accounts.identify(request)
    if caller is None:
        raise Refused(error(401, "signed_out"))
    if caller["role"] not in ENROL_ROLES:
        raise Refused(error(403, "role_cannot_enrol"))
    return caller


class Refused(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


def notice() -> Optional[dict]:
    try:
        with open(ENROLMENT_NOTICE_FILE, encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return None


@router.get("/server-info")
def server_info():
    """Needs no login: the app checks it is talking to the client it was set up for before anyone signs in."""
    current_notice = notice() or {}
    return {"client_id": CLIENT_ID, "client_name": CLIENT_NAME, "notice_version": current_notice.get("version"),
            "notice_url": "/api/v1/notice"}


@router.get("/notice")
def notice_page():
    current_notice = notice()
    return current_notice if current_notice else error(503, "no_notice")


def status_of(row) -> str:
    return "pending" if row["open_job"] else ("enrolled" if row["enrolled_at"] else "none")


@router.get("/persons")
def persons(query: str = "", limit: int = 50, cursor: str = "", caller: dict = Depends(enroller)):
    limit = max(1, min(limit, 100))
    pattern = f"%{query.strip()}%"
    with cursor_source() as db:
        db.execute("""SELECT p.person_id, p.name, p.employee_code, p.department, p.enrolled_at,
                             EXISTS (SELECT 1 FROM enrolment_jobs j WHERE j.person_id = p.person_id AND j.status = 'pending') AS open_job
                      FROM persons p
                      WHERE (p.name ILIKE %s OR p.person_id ILIKE %s OR coalesce(p.employee_code, '') ILIKE %s) AND p.person_id > %s
                      ORDER BY p.person_id LIMIT %s""", (pattern, pattern, pattern, cursor, limit + 1))
        rows = db.fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"persons": [{"person_id": r["person_id"], "name": r["name"], "employee_code": r["employee_code"],
                         **({"department": r["department"]} if r["department"] else {}), "enrolment_status": status_of(r)}
                        for r in rows],
            "next_cursor": rows[-1]["person_id"] if more else None}


# The person's organisational or institutional ID, shown large on the display (owner, 2026-11-03). It names a folder
# and a key prefix, so it starts with a letter or digit (no "." or ".." or hidden folder), and Windows device names
# are refused, as the site folders sit on a Windows host. In Milvus it is only a field value, so "." and "-" are safe.
PERSON_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
WINDOWS_DEVICES = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", re.IGNORECASE)


def person_id_problem(person_id: str) -> Optional[str]:
    if not PERSON_ID.fullmatch(person_id or "") or WINDOWS_DEVICES.fullmatch(person_id):
        return "invalid_person_id"
    return None


class PersonIn(BaseModel):
    person_id: str
    name: str
    department: Optional[str] = None


@router.post("/persons", status_code=201)
def register_person(person: PersonIn, caller: dict = Depends(enroller)):
    """Staff register a person with their organisational ID and full name; the display shows the ID large and the
    name beneath it. The ID is stored as typed, and unique in any letter case."""
    if person_id_problem(person.person_id):
        return error(422, "invalid_person_id")
    name, department = person.name.strip(), (person.department or "").strip() or None
    if not 1 <= len(name) <= 120 or (department and len(department) > 120):
        return error(422, "invalid_name")
    with cursor_source(commit=True) as db:
        db.execute("SELECT 1 FROM persons WHERE lower(person_id) = lower(%s)", (person.person_id,))
        if db.fetchone():
            return error(409, "person_exists")
        db.execute("INSERT INTO persons (person_id, name, department) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING person_id",
                   (person.person_id, name, department))
        if not db.fetchone():  # registered by someone else a moment ago
            return error(409, "person_exists")
    api_logger.info(f"Person {person.person_id} registered by {caller['name']}")
    return {"person_id": person.person_id}


class ConsentIn(BaseModel):
    person_id: str = Field(min_length=1, max_length=128)
    notice_version: str = Field(min_length=1, max_length=64)
    captured_at: datetime
    method: str


@router.post("/consents", status_code=201)
def record_consent(consent: ConsentIn, caller: dict = Depends(enroller)):
    current_notice = notice()
    if not current_notice:
        return error(503, "no_notice")
    if consent.notice_version != str(current_notice.get("version")):
        return error(422, "notice_version_superseded")
    if consent.method != CONSENT_METHOD:
        return error(422, "invalid_method")
    consent_id = str(uuid.uuid4())
    with cursor_source(commit=True) as db:
        db.execute("SELECT 1 FROM persons WHERE person_id = %s", (consent.person_id,))
        if not db.fetchone():
            return error(404, "person_not_found")
        db.execute("INSERT INTO consents (id, person_id, notice_version, captured_at, method, recorded_by) VALUES (%s, %s, %s, %s, %s, %s)",
                   (consent_id, consent.person_id, consent.notice_version, consent.captured_at, consent.method, caller["name"]))
    api_logger.info(f"Consent {consent_id} for {consent.person_id} recorded by {caller['name']}")
    return {"consent_id": consent_id}


@router.delete("/consents/{consent_id}", status_code=202)
def withdraw_consent(consent_id: str, caller: dict = Depends(enroller)):
    """Withdrawal ends the consent and cancels its open job, whose photos are deleted at once. Deleting an accepted
    enrolment's photos and vectors is item 8e, so the deletion is recorded but not yet carried out there."""
    with cursor_source(commit=True) as db:
        db.execute("UPDATE consents SET withdrawn_at = now() WHERE id::text = %s AND withdrawn_at IS NULL RETURNING person_id", (consent_id,))
        if not db.fetchone():
            return error(404, "consent_not_found")
        db.execute("""UPDATE enrolment_jobs SET status = 'rejected', finished_at = now(),
                             problems = '[{"pose": null, "problem": "consent withdrawn"}]'
                      WHERE consent_id::text = %s AND status = 'pending' RETURNING id, poses""", (consent_id,))
        cancelled = db.fetchall()
    for job in cancelled:
        store.delete([f"jobs/{job['id']}/{pose}.jpg" for pose in job["poses"]])
    api_logger.info(f"Consent {consent_id} withdrawn by {caller['name']}; {len(cancelled)} open job(s) cancelled")
    return {"deletion_id": consent_id}


def parse_multipart(content_type: str, body: bytes):
    """(fields, files) as the enrolment app sends them: one part per pose, named by the pose, with a filename."""
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    if not message.is_multipart():
        raise Refused(error(400, "not_multipart"))
    fields, files = {}, {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            raise Refused(error(400, "unnamed_part"))
        payload = part.get_payload(decode=True) or b""
        if part.get_filename() is not None:
            if name in files:
                raise Refused(error(422, "duplicate_pose", pose=name))
            files[name] = payload
        else:
            fields[name] = payload.decode("utf-8", "replace")
    return fields, files


@router.post("/enrolments", status_code=202)
async def create_enrolment(request: Request, caller: dict = Depends(enroller)):
    """202 means durable: every photo is in the bucket and the job is committed, so the app may discard its copies."""
    key = request.headers.get("idempotency-key", "")
    if not key or len(key) > 128:
        return error(400, "idempotency_key_required")
    if int(request.headers.get("content-length") or 0) > ENROLMENT_MAX_BODY_BYTES:
        return error(413, "body_too_large")
    body = await request.body()
    if len(body) > ENROLMENT_MAX_BODY_BYTES:
        return error(413, "body_too_large")
    digest = hashlib.sha256(body).hexdigest()
    with cursor_source() as db:
        db.execute("SELECT id, body_hash FROM enrolment_jobs WHERE idempotency_key = %s", (key,))
        seen = db.fetchone()
    if seen:
        return error(409, "idempotency_key_reused") if seen["body_hash"] != digest else JSONResponse({"job_id": str(seen["id"])}, status_code=202)

    fields, files = parse_multipart(request.headers.get("content-type", ""), body)
    names = set(files)
    if names not in (set(POSES), set(POSES) | set(GLASSES)):
        return error(422, "invalid_pose_set")
    for pose, data in files.items():
        if len(data) > ENROLMENT_MAX_PHOTO_BYTES:
            return error(413, "photo_too_large", pose=pose)
        if not data.startswith(b"\xff\xd8\xff"):
            return error(422, "not_jpeg", pose=pose)
    person_id, consent_id, reason = fields.get("person_id", ""), fields.get("consent_id", ""), fields.get("reason") or None
    if reason is not None and reason not in REASONS:
        return error(422, "invalid_reason")

    with cursor_source() as db:
        db.execute("SELECT enrolled_at FROM persons WHERE person_id = %s", (person_id,))
        person = db.fetchone()
        db.execute("SELECT 1 FROM consents WHERE id::text = %s AND person_id = %s AND withdrawn_at IS NULL", (consent_id, person_id))
        consented = db.fetchone()
        db.execute("SELECT id FROM enrolment_jobs WHERE person_id = %s AND status = 'pending'", (person_id,))
        open_job = db.fetchone()
    if person is None or not consented:
        return error(422, "no_active_consent")
    if open_job:
        return error(409, "enrolment_open", job_id=str(open_job["id"]))
    if person["enrolled_at"] and reason is None:
        return error(422, "reason_required")

    job_id = str(uuid.uuid4())
    for pose, data in files.items():
        store.put(f"jobs/{job_id}/{pose}.jpg", data)
    try:
        with cursor_source(commit=True) as db:
            db.execute("""INSERT INTO enrolment_jobs (id, person_id, consent_id, reason, idempotency_key, body_hash, poses, submitted_by)
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                       (job_id, person_id, consent_id, reason, key, digest, sorted(files), caller["name"]))
    except Exception:
        # A concurrent upload took the key or the person's open slot: drop these photos, then answer as above would
        store.delete([f"jobs/{job_id}/{pose}.jpg" for pose in files])
        with cursor_source() as db:
            db.execute("SELECT id, body_hash FROM enrolment_jobs WHERE idempotency_key = %s", (key,))
            seen = db.fetchone()
            db.execute("SELECT id FROM enrolment_jobs WHERE person_id = %s AND status = 'pending'", (person_id,))
            open_job = db.fetchone()
        if seen:
            return error(409, "idempotency_key_reused") if seen["body_hash"] != digest else JSONResponse({"job_id": str(seen["id"])}, status_code=202)
        if open_job:
            return error(409, "enrolment_open", job_id=str(open_job["id"]))
        raise
    api_logger.info(f"Enrolment job {job_id} for {person_id} ({len(files)} photos) submitted by {caller['name']}")
    return {"job_id": job_id}


@router.get("/enrolments/{job_id}")
def job_status(job_id: str, caller: dict = Depends(enroller)):
    with cursor_source() as db:
        db.execute("SELECT status, problems FROM enrolment_jobs WHERE id::text = %s", (job_id,))
        job = db.fetchone()
    if not job:
        return error(404, "job_not_found")
    # An expired job reads as rejected: the app knows pending, accepted and rejected
    return {"status": "rejected" if job["status"] == "expired" else job["status"], "problems": job["problems"]}


def command(args: list) -> str:
    """The roster command line, against this client's database."""
    import psycopg2
    from parameters import POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login
    user, password = postgres_login()
    rows = [args[1:5]] if args[0] == "add-person" else [
        [row.get("person_id", ""), row.get("name", ""), row.get("employee_code"), row.get("department")]
        for row in csv.DictReader(open(args[1], encoding="utf-8-sig"))]
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, user=user, password=password, host=POSTGRESQL_HOST, port=POSTGRESQL_PORT) as conn, conn.cursor() as cursor:
        cursor.execute(SCHEMA)
        for row in rows:
            person_id, name, code, department = (list(row) + [None, None, None, None])[:4]
            if not person_id or not name or person_id_problem(person_id):
                raise SystemExit(f"a valid person_id (letter or digit first, then letters, digits, . _ -; at most 64) and a name are required: {row}")
            cursor.execute("""INSERT INTO persons (person_id, name, employee_code, department) VALUES (%s, %s, %s, %s)
                              ON CONFLICT (person_id) DO UPDATE SET name = EXCLUDED.name, employee_code = EXCLUDED.employee_code,
                              department = EXCLUDED.department""", (person_id, name, code or None, department or None))
    return f"{len(rows)} person(s) saved"


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("add-person", "import-persons"):
        raise SystemExit(__doc__)
    print(command(sys.argv[1:]))
