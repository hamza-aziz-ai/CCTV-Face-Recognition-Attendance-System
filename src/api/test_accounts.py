"""Accounts on a real PostgreSQL: the role matrix, CSRF, throttling, expiry and revocation, through the running API.
CI runs this against a throwaway PostgreSQL, with IP_ADDRESS, POSTGRES_USER, POSTGRES_PASSWORD, CLIENT_ID=owner and LEGACY_SHARED_SERVICES=1 set."""
import io
import json
import os
import sys
import tempfile
import threading
import time
from unittest import mock

import psycopg2
import requests
import uvicorn

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
# The API reads the camera configuration when imported, and images hold none
os.chdir(tempfile.mkdtemp())
os.makedirs("src/Camera-Configuration")
with open("src/Camera-Configuration/camera_configuration.json", "w") as f:
    json.dump({"maingate": {"api-endpoint": "http://127.0.0.1:9/erp", "cctv-cameras": {"entry": {"cctv-camera-1": {}, "cctv-camera-2": {
        "username": "u", "password": "p@ss", "ip_address": "10.0.0.2", "port": 554, "endpoint": "stream1", "masking-coordinates": None}}, "exit": None}}}, f)

from parameters import LOGIN_ATTEMPTS, POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login  # noqa: E402

USER, PASSWORD = postgres_login()
LOGIN = dict(user=USER, password=PASSWORD, host=POSTGRESQL_HOST, port=POSTGRESQL_PORT)
admin_connection = psycopg2.connect(dbname="postgres", **LOGIN)
admin_connection.autocommit = True
admin_connection.cursor().execute(f'CREATE DATABASE "{POSTGRESQL_DATABASE}"')

import accounts  # noqa: E402
import app as api  # noqa: E402
import enrolment  # noqa: E402
from enrolment_store import MemoryStore  # noqa: E402

api.enrolment_store_override = PHOTOS = MemoryStore()  # MinIO stands in as a dict; the real bucket is tested live

BASE = "http://127.0.0.1:8123"
GOOD = "correct horse battery"


def cli(*args, stdin=""):
    with mock.patch.object(sys, "stdin", io.StringIO(stdin + "\n")):
        return accounts.command(list(args))


def sign_in(name, password=GOOD):
    """Log in; the cookie is Secure, so this plain-HTTP test sends it by hand."""
    r = requests.post(f"{BASE}/auth/login", json={"username": name, "password": password})
    if r.status_code != 200:
        return r.status_code, None
    assert "__Host-session=" in r.headers["set-cookie"] and all(flag in r.headers["set-cookie"].lower() for flag in ("secure", "httponly", "samesite=lax", "path=/")), r.headers["set-cookie"]
    assert "domain" not in r.headers["set-cookie"].lower()
    return 200, {"Cookie": r.headers["set-cookie"].split(";")[0], "X-CSRF-Token": r.json()["csrf_token"]}


def get(path, headers=None):
    return requests.get(f"{BASE}{path}", headers=headers or {}).status_code


def test():
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=8123, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    assert server.started

    cli("add-user", "boss", "client_admin", stdin=GOOD)
    cli("add-user", "staff", "enrolment_operator", stdin=GOOD)
    cli("add-user", "guest", "viewer", stdin=GOOD)
    for bad in (("add-user", "short", "viewer"), ("add-user", "wrong", "root")):
        try:
            cli(*bad, stdin="short" if bad[1] == "short" else GOOD)
        except SystemExit as e:
            assert "password" in str(e) or "Role" in str(e), e
        else:
            raise AssertionError(bad)

    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, **LOGIN) as conn, conn.cursor() as cursor:
        # The database controller creates this table on a host; the live view reads each camera's latest rows from it
        cursor.execute("CREATE TABLE IF NOT EXISTS recognition_results (person_id TEXT, camera_name TEXT, recognition_date DATE, recognition_time TIME, confidence_score REAL)")
        cursor.executemany("INSERT INTO recognition_results VALUES (%s, %s, CURRENT_DATE, %s, %s)",
                           [(f"p{i}", "maingate_entry_cctv-camera-2", f"10:{i:02d}:00", 0.5 + i / 100) for i in range(12)] +
                           [("q", "maingate_exit_cctv-camera-1", "09:00:00", None)])

    route = "/fetch_module_data?date=01-11-2026&module=maingate"
    # No login, and the old key in the URL, are refused
    assert get(route) == 401
    assert get(f"{route}&api_key=anything") == 401
    assert get("/auth/check") == 401
    assert get("/live/check") == 401 and get("/live/events") == 401
    assert requests.post(f"{BASE}/manual_post?date=01-11-2026&location=maingate").status_code == 401

    # Role matrix: every role reads, only the client admin posts to the ERP
    write = f"{BASE}/manual_post?date=01-11-2026&location=nowhere"
    for name, may_write in (("boss", True), ("staff", False), ("guest", False)):
        status, headers = sign_in(name)
        assert status == 200, name
        assert get(route, headers) not in (401, 403), name
        assert get("/auth/check", headers) == 204, name
        assert (requests.post(write, headers=headers).status_code == 403) != may_write, name
        # Live video (D-047): administrators and viewers watch, enrolment staff do not
        may_watch = name != "staff"
        assert get("/live/check", headers) == (204 if may_watch else 403), name
        assert get("/live/cameras", headers) == (200 if may_watch else 403), name
        assert get("/live/events", headers) == (200 if may_watch else 403), name
        assert get("/live", headers) == (200 if may_watch else 403), name

    _, headers = sign_in("guest")
    latest = requests.get(f"{BASE}/live/events", headers=headers).json()
    entry = latest["maingate_entry_cctv-camera-2"]
    assert len(entry) == 10 and entry[0]["person_id"] == "p11" and entry[0]["score"] == 0.61, entry[:2]
    assert latest["maingate_exit_cctv-camera-1"] == [{"person_id": "q", "date": entry[0]["date"], "time": "09:00:00", "score": None}]
    assert requests.get(f"{BASE}/live/cameras", headers=headers).json() == [{"name": "maingate_entry_cctv-camera-2", "path": "maingate_entry_cctv-camera-2"}]

    # CSRF: a session's write needs the token, a read does not
    _, headers = sign_in("boss")
    assert requests.post(write, headers={"Cookie": headers["Cookie"]}).status_code == 403
    assert requests.post(write, headers={"Cookie": headers["Cookie"], "X-CSRF-Token": "wrong"}).status_code == 403
    assert requests.post(write, headers={"Cookie": headers["Cookie"], "X-CSRF-Token": "café".encode()}).status_code == 403

    # Logout ends the session, and a made-up cookie gets nowhere
    assert requests.post(f"{BASE}/auth/logout", headers=headers).status_code == 204
    assert get("/auth/me", headers) == 401
    assert get("/auth/me", {"Cookie": "__Host-session=made-up"}) == 401

    # Expiry
    _, headers = sign_in("guest")
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, **LOGIN) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE sessions SET expires_at = now() - interval '1 minute'")
    assert get("/auth/me", headers) == 401

    # A disabled account's live session stops working, even if its session row survives
    _, headers = sign_in("boss")
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, **LOGIN) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE accounts SET disabled_at = now() WHERE username = 'boss'")
    assert get("/auth/me", headers) == 401
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, **LOGIN) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE accounts SET disabled_at = NULL WHERE username = 'boss'")

    # Disabling a user and changing a password end their sessions
    _, headers = sign_in("staff")
    cli("disable-user", "staff")
    assert get("/auth/me", headers) == 401
    assert sign_in("staff")[0] == 401
    cli("set-password", "staff", stdin="a different long password")
    assert sign_in("staff", "a different long password")[0] == 200
    _, headers = sign_in("staff", "a different long password")
    cli("set-password", "staff", stdin=GOOD)
    assert get("/auth/me", headers) == 401

    # Machine tokens: a role, no CSRF, revocable, and stored only as a hash
    token = cli("add-token", "erp-pull", "viewer")
    bearer = {"Authorization": f"Bearer {token}"}
    assert get(route, bearer) not in (401, 403)
    assert requests.post(write, headers=bearer).status_code == 403
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, **LOGIN) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM machine_tokens WHERE token_hash = %s", (token,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM accounts WHERE password_hash LIKE %s", (f"%{GOOD}%",))
        assert cursor.fetchone()[0] == 0
    assert get("/auth/me", {"Authorization": "Bearer wrong"}) == 401
    cli("revoke-token", "erp-pull")
    assert get(route, bearer) == 401

    # Throttling: the right password stops working after too many failures, for that name only
    for _ in range(LOGIN_ATTEMPTS):
        assert sign_in("guest", "wrong password")[0] == 401
    assert sign_in("guest")[0] == 429
    assert sign_in("boss")[0] == 200
    assert requests.post(f"{BASE}/auth/login", json={"username": "boss", "password": "x" * 129}).status_code == 422
    assert requests.post(f"{BASE}/auth/login", json={"username": "nobody", "password": GOOD}).status_code == 401

    check_enrolment()
    server.should_exit = True
    print("accounts ok (role matrix, live view roles and latest recognitions, CSRF, logout, expiry, disabled users, password change, machine tokens, throttling, no key in the URL)")


def check_enrolment():
    """The enrolment app's contract (D-048): codes it maps, idempotency, one open job, withdrawal, bearer login."""
    cli("add-user", "operator", "enrolment_operator", stdin=GOOD)
    cli("add-user", "watcher", "viewer", stdin=GOOD)
    enrolment.command(["add-person", "p-001", "Asha Rao", "E-1", "Stores"])
    enrolment.command(["add-person", "p-002", "Ravi Kumar"])
    info = requests.get(f"{BASE}/v1/server-info").json()  # no login: the app checks the client before anyone signs in
    assert info == {"client_id": "owner", "client_name": "owner", "notice_version": None, "notice_url": "/api/v1/notice"}, info
    assert requests.get(f"{BASE}/v1/notice").json() == {"error": "no_notice"}

    r = requests.post(f"{BASE}/auth/token", json={"username": "operator", "password": GOOD})
    assert r.status_code == 200 and set(r.json()) == {"token", "role", "expires_at"} and "set-cookie" not in r.headers, r.text
    bearer = {"Authorization": f"Bearer {r.json()['token']}"}
    viewer = {"Authorization": f"Bearer {requests.post(f'{BASE}/auth/token', json={'username': 'watcher', 'password': GOOD}).json()['token']}"}
    assert requests.post(f"{BASE}/auth/token", json={"username": "operator", "password": "wrong password!"}).status_code == 401
    assert requests.get(f"{BASE}/v1/persons").json() == {"error": "signed_out"}
    assert requests.get(f"{BASE}/v1/persons", headers=viewer).json() == {"error": "role_cannot_enrol"}
    roster = requests.get(f"{BASE}/v1/persons?query=asha", headers=bearer).json()
    assert roster == {"persons": [{"person_id": "p-001", "name": "Asha Rao", "employee_code": "E-1", "department": "Stores",
                                   "enrolment_status": "none"}], "next_cursor": None}, roster
    page = requests.get(f"{BASE}/v1/persons?limit=1", headers=bearer).json()
    assert page["next_cursor"] == "p-001" and len(page["persons"]) == 1
    assert requests.get(f"{BASE}/v1/persons?limit=1&cursor=p-001", headers=bearer).json()["persons"][0]["person_id"] == "p-002"

    consent = {"person_id": "p-001", "notice_version": "1", "captured_at": "2026-11-03T12:00:00+05:30", "method": "staff_attested_in_app"}
    assert requests.post(f"{BASE}/v1/consents", json=consent, headers=bearer).json() == {"error": "no_notice"}
    os.makedirs("enrolment", exist_ok=True)
    with open("enrolment/notice.json", "w") as f:
        json.dump({"version": "2", "effective_date": "2026-11-03", "controller": "Test", "contact": {"name": "x", "email": "x@example.com"}, "sections": []}, f)
    assert requests.get(f"{BASE}/v1/server-info").json()["notice_version"] == "2"
    assert requests.post(f"{BASE}/v1/consents", json=consent, headers=bearer).json() == {"error": "notice_version_superseded"}
    r = requests.post(f"{BASE}/v1/consents", json={**consent, "notice_version": "2"}, headers=bearer)
    assert r.status_code == 201, r.text
    consent_id = r.json()["consent_id"]

    jpeg = bytes.fromhex("ffd8ffe0") + b"0" * 100
    def upload(key, poses=enrolment.POSES, person="p-001", consent_to=None, **extra):
        files = [(pose, (f"{pose}.jpg", jpeg, "image/jpeg")) for pose in poses]
        prepared = requests.Request("POST", f"{BASE}/v1/enrolments", files=files,
                                    data={"person_id": person, "consent_id": consent_to or consent_id, **extra}).prepare()
        return prepared, (lambda body=prepared.body, headers=None: requests.post(
            f"{BASE}/v1/enrolments", data=body, headers={**bearer, "Content-Type": prepared.headers["Content-Type"], **({"Idempotency-Key": key} if key else {}), **(headers or {})}))
    _, send = upload(None)
    assert send().json() == {"error": "idempotency_key_required"}
    assert upload("k0", enrolment.POSES[:4])[1]().json() == {"error": "invalid_pose_set"}
    assert upload("k0", person="p-002")[1]().json() == {"error": "no_active_consent"}
    prepared, send = upload("k1")
    first = send()
    assert first.status_code == 202, first.text
    job_id = first.json()["job_id"]
    assert sorted(PHOTOS.objects) == sorted(f"jobs/{job_id}/{pose}.jpg" for pose in enrolment.POSES)
    assert send().json() == {"job_id": job_id}, "the same key and body must return the same job"
    assert upload("k1", reason="other")[1]().json() == {"error": "idempotency_key_reused"}
    assert upload("k2")[1]().json() == {"error": "enrolment_open", "job_id": job_id}
    assert requests.get(f"{BASE}/v1/enrolments/{job_id}", headers=bearer).json() == {"status": "pending", "problems": []}
    assert requests.get(f"{BASE}/v1/enrolments/{job_id}", headers=viewer).status_code == 403
    assert requests.get(f"{BASE}/v1/persons?query=p-001", headers=bearer).json()["persons"][0]["enrolment_status"] == "pending"

    # Withdrawal cancels the open job and deletes its photos at once
    assert requests.delete(f"{BASE}/v1/consents/{consent_id}", headers=bearer).status_code == 202
    assert requests.get(f"{BASE}/v1/enrolments/{job_id}", headers=bearer).json() == {"status": "rejected", "problems": [{"pose": None, "problem": "consent withdrawn"}]}
    assert PHOTOS.objects == {}
    assert upload("k3")[1]().json() == {"error": "no_active_consent"}
    print("enrolment ok (bearer login, roles, roster paging, notice and consent, idempotency, one open job, withdrawal deletes photos)")


def test_live_config():
    """MediaMTX serves HLS only, pulls each camera on demand over TCP, and its file, which holds passwords, is private."""
    import live
    text = live.mediamtx_config(live.cameras())
    for line in ("rtsp: no", "rtmp: no", "webrtc: no", "srt: no", "moq: no", "api: no", "hls: yes", "  live/maingate_entry_cctv-camera-2:",
                 '    source: "rtsp://u:p%40ss@10.0.0.2:554/stream1"', "    sourceOnDemand: yes", "    rtspTransport: tcp"):
        assert line in text.splitlines(), line
    assert "cctv-camera-1" not in text, "an entry with no address must be left out"
    assert live.mediamtx_config({}).splitlines()[-1] == "paths: {}"
    assert live.path_name("gate 1/a") == "gate_1_a"
    path = os.path.join(tempfile.mkdtemp(), "mediamtx.yml")
    assert live.write_config(path) == 1 and open(path).read() == text
    assert os.stat(path).st_mode & 0o077 == 0, oct(os.stat(path).st_mode)
    print("live view config ok (HLS only, on demand over TCP, unfinished cameras left out, file private)")


if __name__ == "__main__":
    test_live_config()
    test()
