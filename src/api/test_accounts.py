"""Accounts on a real PostgreSQL: the role matrix, CSRF, throttling, expiry and revocation, through the running API.
CI runs this against a throwaway PostgreSQL, with IP_ADDRESS, POSTGRES_USER, POSTGRES_PASSWORD, CLIENT_ID=owner and LEGACY_SHARED_SERVICES=1 set."""
import http.server
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
import edge  # noqa: E402
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
    check_edge()
    server.should_exit = True
    print("accounts ok (role matrix, live view roles and latest recognitions, CSRF, logout, expiry, disabled users, password change, machine tokens, throttling, no key in the URL)")


def check_edge():
    """Edge face crops (D-043): only an edge_collector machine token gets through, to this client's collector only."""
    received = []

    class Collector(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.rfile.read(int(self.headers["Content-Length"])), self.headers.get("Authorization")))
            body = b'{"message": "1 succeeded, 1 failed", "failures": [{"index": 1}]}'
            self.send_response(207)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    collector = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=collector.serve_forever, daemon=True).start()
    url = f"{BASE}/v1/edge/faces"
    crops = b'[{"person_id": "p-001"}]'
    try:
        cli("add-user", "edge-person", "edge_collector", stdin=GOOD)
        raise AssertionError("a person must not hold the edge_collector role")
    except SystemExit:
        pass
    edge_token = {"Authorization": f"Bearer {cli('add-token', 'jetson-1', 'edge_collector')}"}
    viewer = {"Authorization": f"Bearer {cli('add-token', 'erp-read', 'viewer')}"}
    with mock.patch.object(edge, "COLLECTOR", f"http://127.0.0.1:{collector.server_port}/faces"):
        assert requests.post(url, data=crops).status_code == 401
        assert requests.post(url, data=crops, headers={"Authorization": "Bearer another-clients-token"}).status_code == 401
        assert requests.post(url, data=crops, headers=viewer).status_code == 403
        assert not received
        r = requests.post(url, data=crops, headers=edge_token)
        assert r.status_code == 207 and r.json()["failures"] == [{"index": 1}], r.text  # the collector's partial answer reaches the edge
        assert received == [(crops, None)], received  # the edge's token stops at the API
        assert requests.post(url, data=b"x" * (edge.MAX_BODY + 1), headers=edge_token).status_code == 413
        # The token opens nothing else: not the proxy's page gate, the live view, enrolment or reports
        for path in ("/auth/check", "/auth/me", "/live/cameras", "/fetch_module_data"):
            assert get(path, edge_token) == 403, path
        assert requests.get(f"{BASE}/v1/persons", headers=edge_token).json() == {"error": "role_cannot_enrol"}
        collector.shutdown()
        collector.server_close()
        assert requests.post(url, data=crops, headers=edge_token).json() == {"error": "collector_unavailable"}
        cli("revoke-token", "jetson-1")
        assert requests.post(url, data=crops, headers=edge_token).status_code == 401
    assert len(received) == 1
    print("edge crops ok (edge_collector token forwarded with the collector's 207, missing, unknown, wrong-role and revoked tokens refused, too large refused, nothing else opened)")


def check_enrolment():
    """The enrolment app's contract (D-048): codes it maps, idempotency, one open job, withdrawal, bearer login."""
    cli("add-user", "operator", "enrolment_operator", stdin=GOOD)
    cli("add-user", "watcher", "viewer", stdin=GOOD)
    enrolment.command(["add-person", "p-001", "Asha Rao", "E-1", "Stores"])
    enrolment.command(["add-person", "p-002", "Ravi Kumar"])
    info = requests.get(f"{BASE}/v1/server-info").json()  # no login: the app checks the client before anyone signs in
    assert info == {"client_id": "owner", "client_name": "owner", "notice_version": None, "notice_url": "/api/v1/notice", "deletion_days": 90}, info
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

    # Registration (owner, 2026-11-03): the organisational ID and the full name, ID unique in any letter case
    register = lambda body, who=bearer: requests.post(f"{BASE}/v1/persons", json=body, headers=who)
    r = register({"person_id": "EMP-0042.a", "name": "  Meera Iyer  ", "department": "HR"})
    assert r.status_code == 201 and r.json() == {"person_id": "EMP-0042.a"}, r.text
    assert register({"person_id": "emp-0042.A", "name": "Someone"}).json() == {"error": "person_exists"}
    for bad in (".hidden", "..", "CON", "nul.txt", "a b", "x/y", "a" * 65, ""):
        assert register({"person_id": bad, "name": "X"}).json() == {"error": "invalid_person_id"}, bad
    assert register({"person_id": "ok-1", "name": "   "}).json() == {"error": "invalid_name"}
    assert register({"person_id": "ok-1", "name": "X"}, viewer).json() == {"error": "role_cannot_enrol"}
    meera = requests.get(f"{BASE}/v1/persons?query=meera", headers=bearer).json()["persons"]
    assert meera == [{"person_id": "EMP-0042.a", "name": "Meera Iyer", "employee_code": None, "department": "HR", "enrolment_status": "none"}], meera

    consent = {"person_id": "p-001", "notice_version": "1", "captured_at": "2026-11-03T12:00:00+05:30", "method": "staff_attested_in_app"}
    assert requests.post(f"{BASE}/v1/consents", json=consent, headers=bearer).json() == {"error": "no_notice"}
    os.makedirs("enrolment", exist_ok=True)
    # Responsible party and contact come only from the site's notice: one missing, or a template placeholder left in, is not served
    for unfilled in ({"version": "2", "controller": "Test", "contact": {"name": "x"}, "sections": []},
                     {"version": "2", "controller": "<client organisation>", "contact": {"name": "x", "email": "x@example.com"}, "sections": []}):
        with open("enrolment/notice.json", "w") as f:
            json.dump(unfilled, f)
        assert requests.get(f"{BASE}/v1/notice").json() == {"error": "no_notice"}, unfilled
    with open("enrolment/notice.json", "w") as f:
        json.dump({"version": "2", "effective_date": "2026-11-03", "controller": "Test", "contact": {"name": "x", "email": "x@example.com"}, "sections": []}, f)
    assert requests.get(f"{BASE}/v1/server-info").json()["notice_version"] == "2"
    assert requests.post(f"{BASE}/v1/consents", json=consent, headers=bearer).json() == {"error": "notice_version_superseded"}
    r = requests.post(f"{BASE}/v1/consents", json={**consent, "notice_version": "2"}, headers=bearer)
    assert r.status_code == 201, r.text
    consent_id = r.json()["consent_id"]
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, **LOGIN) as conn, conn.cursor() as db:
        db.execute("SELECT notice->>'controller', notice->'contact'->>'email' FROM consents WHERE id = %s", (consent_id,))
        assert db.fetchone() == ("Test", "x@example.com")  # the consent keeps who was responsible when it was given

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
    assert requests.get(f"{BASE}/v1/enrolments/{job_id}", headers=bearer).json() == {"status": "rejected", "problems": [{"pose": None, "problem": "consent withdrawn", "code": "withdrawn"}]}
    assert PHOTOS.objects == {}
    assert upload("k3")[1]().json() == {"error": "no_active_consent"}
    print("enrolment ok (bearer login, roles, registration with ID rules, roster paging, notice and consent, idempotency, one open job, withdrawal deletes photos)")
    check_deletion(bearer, viewer, consent, upload, jpeg)


def check_deletion(bearer, viewer, consent, upload, jpeg):
    """8e: a withdrawal or a leaver deletes the person's face data; attendance records stay, their pictures cleared later."""
    import pickle
    from contextlib import closing
    import psycopg2.extras
    import enrolment_deletion
    from parameters import POSTGRESQL_DATABASE_NAME
    give = lambda: requests.post(f"{BASE}/v1/consents", json={**consent, "notice_version": "2"}, headers=bearer)  # noqa: E731
    sql = lambda query, args=(), db=POSTGRESQL_DATABASE: _sql(db, query, args)  # noqa: E731
    assert requests.get(f"{BASE}/v1/server-info").json()["deletion_days"] == 90

    # p-001 enrolled, as the worker leaves an accepted job: photos under persons/, enrolled_at set
    accepted_consent = give().json()["consent_id"]
    job = upload("k4", consent_to=accepted_consent)[1]().json()["job_id"]
    sql("UPDATE enrolment_jobs SET status = 'accepted', finished_at = now() WHERE id = %s", (job,))
    sql("UPDATE persons SET enrolled_at = now() WHERE person_id = 'p-001'")
    PHOTOS.objects = {f"persons/p-001/{pose}.jpg": jpeg for pose in enrolment.POSES}

    # A withdrawal during a re-enrolment ends only that attempt
    retake_consent = give().json()["consent_id"]
    retake = upload("k5", consent_to=retake_consent, reason="other")[1]().json()["job_id"]
    assert requests.delete(f"{BASE}/v1/consents/{retake_consent}", headers=bearer).json() == {"deletion_id": retake_consent}
    assert sorted(PHOTOS.objects) == sorted(f"persons/p-001/{pose}.jpg" for pose in enrolment.POSES), "only the retake's photos go"
    assert requests.get(f"{BASE}/v1/persons?query=p-001", headers=bearer).json()["persons"][0]["enrolment_status"] == "enrolled"
    assert requests.get(f"{BASE}/v1/enrolments/{retake}", headers=bearer).json()["problems"][0]["code"] == "withdrawn"

    # Withdrawing the consent the enrolment rests on requests the deletion; the route returns the same open request
    deletion_id = requests.delete(f"{BASE}/v1/consents/{accepted_consent}", headers=bearer).json()["deletion_id"]
    assert deletion_id != accepted_consent
    delete = lambda person, who=bearer, reason="left": requests.delete(f"{BASE}/v1/persons/{person}/enrolment?reason={reason}", headers=who)  # noqa: E731
    assert delete("p-001", reason="bogus").json() == {"error": "invalid_reason"}
    assert delete("p-001", viewer).json() == {"error": "role_cannot_enrol"}
    assert delete("nobody").json() == {"error": "person_not_found"}
    r = delete("p-001")
    assert r.status_code == 202 and r.json() == {"deletion_id": deletion_id}, r.text
    assert requests.get(f"{BASE}/v1/persons?query=p-001", headers=bearer).json()["persons"][0]["enrolment_status"] == "none"
    assert give().json() == {"error": "deletion_pending"}
    assert sql("SELECT count(*) AS n FROM consents WHERE person_id = 'p-001' AND withdrawn_at IS NULL")[0]["n"] == 0

    # What the worker deletes: folders (dataset, crops, portrait), the nightly vectors, the collector's rows, Milvus, the rows
    root = tempfile.mkdtemp()
    folders = [os.path.join(root, name) for name in ("faces", "crops", "portraits")]
    for folder in folders:
        for person in ("p-001", "p-002"):
            os.makedirs(os.path.join(folder, person))
    nightly = os.path.join(root, "dynamic-dataset.pkl")
    with open(nightly, "wb") as file:
        pickle.dump({"names": ["p-001", "p-002", "p-001"], "encodings": [1, 2, 3]}, file)
    admin_connection.cursor().execute(f'CREATE DATABASE "{POSTGRESQL_DATABASE_NAME}"')
    sql("CREATE TABLE person_summary (person_id VARCHAR PRIMARY KEY); CREATE TABLE face_images (person_id VARCHAR REFERENCES person_summary, image BYTEA);"
        "INSERT INTO person_summary VALUES ('p-001'), ('p-002'); INSERT INTO face_images VALUES ('p-001', 'x'), ('p-002', 'y')", db=POSTGRESQL_DATABASE_NAME)
    forgotten = []

    def milvus_down(_):
        raise RuntimeError("Milvus down")

    with closing(psycopg2.connect(dbname=POSTGRESQL_DATABASE, cursor_factory=psycopg2.extras.RealDictCursor, **LOGIN)) as conn:
        try:
            enrolment_deletion.run_one(conn, PHOTOS, milvus_down, folders=folders, pickle_path=nightly)
        except RuntimeError:
            pass
        assert sql("SELECT done_at FROM deletions WHERE id = %s", (deletion_id,))[0]["done_at"] is None, "a failed deletion must stay open"
        assert sql("SELECT 1 FROM persons WHERE person_id = 'p-001'"), "the rows go last, so a retry still knows the person"
        assert enrolment_deletion.run_one(conn, PHOTOS, forgotten.append, folders=folders, pickle_path=nightly)
        assert not enrolment_deletion.run_one(conn, PHOTOS, forgotten.append, folders=folders, pickle_path=nightly)
    assert forgotten == ["p-001"]
    assert PHOTOS.objects == {}
    assert all(not os.path.exists(os.path.join(folder, "p-001")) and os.path.isdir(os.path.join(folder, "p-002")) for folder in folders)
    with open(nightly, "rb") as file:
        assert pickle.load(file) == {"names": ["p-002"], "encodings": [2]}
    assert sql("SELECT person_id FROM face_images", db=POSTGRESQL_DATABASE_NAME) == [{"person_id": "p-002"}]
    assert sql("SELECT person_id FROM person_summary", db=POSTGRESQL_DATABASE_NAME) == [{"person_id": "p-002"}]
    for table in ("persons", "consents", "enrolment_jobs"):
        assert not sql(f"SELECT 1 FROM {table} WHERE person_id = 'p-001'"), table
    assert sql("SELECT done_at FROM deletions WHERE id = %s", (deletion_id,))[0]["done_at"] is not None
    try:
        enrolment_deletion.remove_folder(folders[0], "..")
    except ValueError:
        pass
    else:
        raise AssertionError("an ID pointing outside the dataset must be refused")
    assert requests.post(f"{BASE}/v1/persons", json={"person_id": "p-001", "name": "Asha Rao"}, headers=bearer).status_code == 201, "the ID is free again"

    # Attendance records stay; their camera pictures are cleared 3 years after the request, records made since keep theirs
    sql("ALTER TABLE recognition_results ADD COLUMN IF NOT EXISTS recognition_frame BYTEA; DELETE FROM recognition_results;"
        "UPDATE deletions SET requested_at = now() - interval '3 years 1 day' WHERE id = %s;"
        "INSERT INTO recognition_results (person_id, recognition_date, recognition_frame) VALUES ('p-001', current_date - interval '3 years 2 days', 'old'), "
        "('p-001', current_date, 'new'), ('p-002', current_date - interval '3 years 2 days', 'other')", (deletion_id,))
    with closing(psycopg2.connect(dbname=POSTGRESQL_DATABASE, cursor_factory=psycopg2.extras.RealDictCursor, **LOGIN)) as conn:
        assert enrolment_deletion.clear_frames(conn) == 1
        assert enrolment_deletion.clear_frames(conn) == 0
    frames = sql("SELECT person_id, recognition_frame IS NULL AS cleared FROM recognition_results ORDER BY recognition_date, person_id")
    assert frames == [{"person_id": "p-001", "cleared": True}, {"person_id": "p-002", "cleared": False}, {"person_id": "p-001", "cleared": False}], frames
    print("deletion ok (withdrawal or leaver, retake withdrawal kept apart, everything of the face deleted, retried whole, records kept, pictures cleared at 3 years)")


def _sql(db, query, args=()):
    import psycopg2.extras
    with psycopg2.connect(dbname=db, cursor_factory=psycopg2.extras.RealDictCursor, **LOGIN) as conn, conn.cursor() as cursor:
        cursor.execute(query, args)
        return cursor.fetchall() if cursor.description else None


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
