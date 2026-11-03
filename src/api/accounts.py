"""Local accounts, sessions and machine tokens for one client's stack (D-036 step 4, D-039).

Each client's accounts live in its own database, so a login cannot reach another client. Run in the API container:
  python3 src/api/accounts.py add-user NAME ROLE        password from stdin
  python3 src/api/accounts.py set-password NAME         password from stdin; ends the user's sessions
  python3 src/api/accounts.py disable-user NAME         ends the user's sessions
  python3 src/api/accounts.py add-token NAME ROLE       prints the token once
  python3 src/api/accounts.py revoke-token NAME
"""
import getpass
import hashlib
import hmac
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

current = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.dirname(current))

from custom_logging import api_logger  # noqa: E402
from parameters import LOGIN_ATTEMPTS, LOGIN_WINDOW_MINUTES, SESSION_HOURS  # noqa: E402

ROLES = ("client_admin", "enrolment_operator", "viewer")
COOKIE = "__Host-session"  # the prefix makes browsers require Secure, Path=/ and no Domain: a host-only cookie
PASSWORD_LENGTHS = (12, 128)
SCRYPT = {"n": 2 ** 17, "r": 8, "p": 1, "maxmem": 256 * 1024 * 1024, "dklen": 32}  # OWASP's minimum for scrypt

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    disabled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS machine_tokens (
    token_hash TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    revoked_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS login_failures (
    username TEXT NOT NULL,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

with open(os.path.join(current, "sign_in.html"), encoding="utf-8") as page:
    SIGN_IN_PAGE = page.read()

router = APIRouter(prefix="/auth")
cursor_source: Optional[Callable] = None  # app.py's get_db_cursor


def digest(token: str) -> str:
    """Tokens are long and random, so a plain hash is enough to keep them useless if the table leaks."""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}${hashlib.scrypt(password.encode(), salt=salt, **SCRYPT).hex()}"


def password_matches(password: str, stored: str) -> bool:
    salt, expected = stored.split("$")
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT).hex(), expected)


UNKNOWN_USER_HASH = hash_password(secrets.token_urlsafe(16))  # an unknown name costs the same time as a wrong password


def setup(get_cursor: Callable):
    global cursor_source
    cursor_source = get_cursor
    with get_cursor(commit=True) as cursor:
        cursor.execute(SCHEMA)


def identify(request: Request) -> Optional[dict]:
    """Who is calling: a machine by its bearer token, or a person by their session cookie."""
    header = request.headers.get("authorization", "")
    with cursor_source(commit=False) as cursor:
        if header.lower().startswith("bearer "):
            token_hash = digest(header[7:].strip())
            cursor.execute("SELECT name, role FROM machine_tokens WHERE token_hash = %s AND revoked_at IS NULL", (token_hash,))
            row = cursor.fetchone()
            if row:
                return {"name": row["name"], "role": row["role"], "csrf": None}
            # A person's session from /auth/token, as the enrolment app sends it: a header, not a cookie, so no CSRF
            cursor.execute("""SELECT a.username, a.role FROM sessions s JOIN accounts a ON a.id = s.account_id
                              WHERE s.token_hash = %s AND s.expires_at > now() AND a.disabled_at IS NULL""", (token_hash,))
            row = cursor.fetchone()
            return {"name": row["username"], "role": row["role"], "csrf": None, "session": token_hash} if row else None
        token = request.cookies.get(COOKIE)
        if not token:
            return None
        cursor.execute("""SELECT a.username, a.role, s.csrf_token, s.token_hash FROM sessions s JOIN accounts a ON a.id = s.account_id
                          WHERE s.token_hash = %s AND s.expires_at > now() AND a.disabled_at IS NULL""", (digest(token),))
        row = cursor.fetchone()
        return {"name": row["username"], "role": row["role"], "csrf": row["csrf_token"], "session": row["token_hash"]} if row else None


def require(*allowed: str):
    """A route dependency: refuse unknown callers and wrong roles, and require the CSRF token on a session's writes."""
    def check(request: Request) -> dict:
        caller = identify(request)
        if caller is None:
            raise HTTPException(status_code=401, detail="Not signed in")
        if caller["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Your role does not allow this")
        if caller["csrf"] and request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), caller["csrf"].encode()):
                raise HTTPException(status_code=403, detail="Missing or wrong CSRF token")
        return caller
    return check


signed_in = require(*ROLES)
admin = require("client_admin")


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=PASSWORD_LENGTHS[1])  # scrypt's cost should not depend on a caller's input size


@router.get("/sign-in", response_class=HTMLResponse)
def sign_in_page():
    return SIGN_IN_PAGE


def start_session(credentials: Login) -> tuple:
    """Checks a login, with throttling, and opens a session: (account, token, csrf token). Raises 401 or 429."""
    with cursor_source(commit=True) as cursor:
        cursor.execute("DELETE FROM login_failures WHERE failed_at < now() - make_interval(mins => %s)", (LOGIN_WINDOW_MINUTES,))
        cursor.execute("DELETE FROM sessions WHERE expires_at < now()")
        cursor.execute("SELECT count(*) AS failures FROM login_failures WHERE username = %s", (credentials.username,))
        if cursor.fetchone()["failures"] >= LOGIN_ATTEMPTS:
            api_logger.warning(f"Login throttled for {credentials.username}")
            raise HTTPException(status_code=429, detail="Too many failed logins; try again later")
        cursor.execute("SELECT id, role, password_hash FROM accounts WHERE username = %s AND disabled_at IS NULL", (credentials.username,))
        account = cursor.fetchone()
        matches = password_matches(credentials.password, account["password_hash"] if account else UNKNOWN_USER_HASH)
        if not (account and matches):
            cursor.execute("INSERT INTO login_failures (username) VALUES (%s)", (credentials.username,))
            api_logger.warning(f"Failed login for {credentials.username}")
            failed = True
        else:
            failed = False
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            cursor.execute("DELETE FROM login_failures WHERE username = %s", (credentials.username,))
            cursor.execute("INSERT INTO sessions (token_hash, account_id, csrf_token, expires_at) VALUES (%s, %s, %s, now() + make_interval(hours => %s))",
                           (digest(token), account["id"], csrf, SESSION_HOURS))
    if failed:  # raised out here, so the failure above commits
        raise HTTPException(status_code=401, detail="Wrong username or password")
    api_logger.info(f"Login by {credentials.username}")
    return account, token, csrf


@router.post("/login")
def login(credentials: Login, response: Response):
    """Browsers: the session goes in an HttpOnly cookie, out of reach of page scripts, and writes need the CSRF token."""
    account, token, csrf = start_session(credentials)
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, secure=True, httponly=True, samesite="lax", path="/")
    return {"username": credentials.username, "role": account["role"], "csrf_token": csrf}


@router.post("/token")
def token(credentials: Login):
    """The enrolment app (owner, 2026-11-03): the same session, returned for an Authorization: Bearer header. No cookie,
    so the browser pages keep theirs out of script reach."""
    account, session_token, _ = start_session(credentials)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    return {"token": session_token, "role": account["role"], "expires_at": expires.isoformat(timespec="seconds")}


@router.post("/logout", status_code=204)
def logout(response: Response, caller: dict = Depends(signed_in)):
    if caller.get("session"):
        with cursor_source(commit=True) as cursor:
            cursor.execute("DELETE FROM sessions WHERE token_hash = %s", (caller["session"],))
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax", path="/")


@router.get("/me")
def me(caller: dict = Depends(signed_in)):
    return {"name": caller["name"], "role": caller["role"], "csrf_token": caller["csrf"]}


@router.get("/check", status_code=204)
def check(caller: dict = Depends(signed_in)):
    """For the reverse proxy: 204 lets a request through to a protected page, 401 stops it."""


def command(args: list) -> str:
    """The accounts command line, against this client's database. Returns what to print."""
    import psycopg2
    from parameters import POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login

    user, password = postgres_login()
    action, name = args[0], args[1]
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, user=user, password=password, host=POSTGRESQL_HOST, port=POSTGRESQL_PORT) as conn, conn.cursor() as cursor:
        cursor.execute(SCHEMA)
        if action in ("add-user", "add-token") and args[2] not in ROLES:
            raise SystemExit(f"Role must be one of {', '.join(ROLES)}")
        if action in ("add-user", "set-password"):
            secret = sys.stdin.readline().strip() if not sys.stdin.isatty() else getpass.getpass("Password: ")
            if not PASSWORD_LENGTHS[0] <= len(secret) <= PASSWORD_LENGTHS[1]:
                raise SystemExit(f"The password must be {PASSWORD_LENGTHS[0]} to {PASSWORD_LENGTHS[1]} characters")
        if action == "add-user":
            cursor.execute("INSERT INTO accounts (username, password_hash, role) VALUES (%s, %s, %s)", (name, hash_password(secret), args[2]))
            return f"User {name} added as {args[2]}"
        if action == "set-password":
            cursor.execute("UPDATE accounts SET password_hash = %s, disabled_at = NULL WHERE username = %s", (hash_password(secret), name))
        elif action == "disable-user":
            cursor.execute("UPDATE accounts SET disabled_at = now() WHERE username = %s", (name,))
        elif action == "add-token":
            token = secrets.token_urlsafe(32)
            cursor.execute("INSERT INTO machine_tokens (token_hash, name, role) VALUES (%s, %s, %s)", (digest(token), name, args[2]))
            return token
        elif action == "revoke-token":
            cursor.execute("UPDATE machine_tokens SET revoked_at = now() WHERE name = %s", (name,))
        else:
            raise SystemExit(__doc__)
        if cursor.rowcount != 1:
            raise SystemExit(f"No such name: {name}")
        cursor.execute("DELETE FROM sessions WHERE account_id IN (SELECT id FROM accounts WHERE username = %s)", (name,))
        return f"{action}: {name}"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    print(command(sys.argv[1:]))
