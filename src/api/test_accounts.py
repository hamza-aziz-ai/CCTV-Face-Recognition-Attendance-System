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
    json.dump({"maingate": {"api-endpoint": "http://127.0.0.1:9/erp", "cctv-cameras": {"entry": {"cctv-camera-1": {}}, "exit": None}}}, f)

from parameters import LOGIN_ATTEMPTS, POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login  # noqa: E402

USER, PASSWORD = postgres_login()
LOGIN = dict(user=USER, password=PASSWORD, host=POSTGRESQL_HOST, port=POSTGRESQL_PORT)
admin_connection = psycopg2.connect(dbname="postgres", **LOGIN)
admin_connection.autocommit = True
admin_connection.cursor().execute(f'CREATE DATABASE "{POSTGRESQL_DATABASE}"')

import accounts  # noqa: E402
import app as api  # noqa: E402

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

    route = "/fetch_module_data?date=01-11-2026&module=maingate"
    # No login, and the old key in the URL, are refused
    assert get(route) == 401
    assert get(f"{route}&api_key=anything") == 401
    assert get("/auth/check") == 401
    assert requests.post(f"{BASE}/manual_post?date=01-11-2026&location=maingate").status_code == 401

    # Role matrix: every role reads, only the client admin posts to the ERP
    write = f"{BASE}/manual_post?date=01-11-2026&location=nowhere"
    for name, may_write in (("boss", True), ("staff", False), ("guest", False)):
        status, headers = sign_in(name)
        assert status == 200, name
        assert get(route, headers) not in (401, 403), name
        assert get("/auth/check", headers) == 204, name
        assert (requests.post(write, headers=headers).status_code == 403) != may_write, name

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

    server.should_exit = True
    print("accounts ok (role matrix, CSRF, logout, expiry, disabled users, password change, machine tokens, throttling, no key in the URL)")


if __name__ == "__main__":
    test()
