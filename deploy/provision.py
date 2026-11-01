"""Provisions one client on this host's shared services (D-036 step 3), with admin rights the client's stack never gets.

Per client <c>, each confined to its own data (the owner keeps its database and collection names, D-036):
  PostgreSQL  role <c>_app owning <c>_cctv_camera_surveillance and <c>_face_recognition_database; nobody else connects
  Milvus      user <c>_app with a role over database <c>_default only, enough to publish (D-030: collections, alias),
              and an empty first version behind the alias plus the staging collection
  Kafka       SCRAM users <c>_app (write) and <c>_display (read, for displays) on topics and groups prefixed "<c>.",
              and the topics themselves, one per point with one partition per camera, from the site's cameras
  MinIO       bucket <c>-enrolment and access key <c>-app with a policy for that bucket only (dataset store)

The client's passwords are generated once and saved to sites/<c>/.env before any service is touched, so a rerun after
a failure reuses them and finishes the job. A principal that exists while its password is not saved is never reset
behind the running stack's back: provisioning stops and says how to recover. Nothing secret is printed.

  python provision.py CLIENT              provision (or finish provisioning) one client; safe to rerun, and rerun it
                                          after changing the client's cameras (topics and partitions follow them)
  python provision.py --init-milvus-root  once per host, before Milvus authorisation is on: replace root's default password
  python provision.py --init-kafbat       once per host: a read-only Kafka login for the Kafbat UI
Options: --sites DIR, --admin-env FILE (holds MILVUS_ROOT_PASSWORD), --postgres/--kafka/--store CONTAINER, --milvus URL.
Stdlib only, like watch.py: the services' own command-line tools run inside their containers through docker exec.
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT_ID = re.compile(r"[a-z][a-z0-9]{2,29}")  # same rule as src/parameters.py
OWNER = "owner"
MILVUS_GROUPS = ("DatabaseReadWrite", "DatabaseAdmin", "CollectionAdmin")  # inside its own database only
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Stop(Exception):
    """A refusal the owner must act on; the message carries no secret."""


def databases(client):
    """The client's two PostgreSQL databases; the owner keeps the names its data already has (D-036)."""
    if client == OWNER:
        return ["CCTV_Camera_Surveillance", "Face_Recognition_Database"]
    return [f"{client}_cctv_camera_surveillance", f"{client}_face_recognition_database"]


def milvus_database(client):
    return "default" if client == OWNER else f"{client}_default"


def settings(client):
    """Every name for a client, and the passwords' keys in its site .env. The owner keeps legacy names: step 3c."""
    return {
        "PG_APP_USER": f"{client}_app", "MILVUS_APP_USER": f"{client}_app", "KAFKA_APP_USER": f"{client}_app",
        "KAFKA_DISPLAY_USER": f"{client}_display", "STORE_APP_ACCESS_KEY": f"{client}-app",
        "PG_APP_PASSWORD": None, "MILVUS_APP_PASSWORD": None, "KAFKA_APP_PASSWORD": None,
        "KAFKA_DISPLAY_PASSWORD": None, "STORE_APP_SECRET_KEY": None,
    }


def read_env(path):
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.lstrip().startswith("#"))


def save_missing(path, wanted):
    """Append the keys path lacks (None: a new password), atomically: a crash leaves the old file or the new one."""
    current = read_env(path)
    fresh = {k: v if v is not None else secrets.token_hex(16) for k, v in wanted.items() if k not in current}
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        text += ("" if not text or text.endswith("\n") else "\n") + "".join(f"{k}={v}\n" for k, v in fresh.items())
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)  # best effort on Windows
        os.replace(tmp, path)
    return read_env(path)


def run(cmd, stdin=None, secret=()):
    """Run a command; on failure raise with its last error line, every secret blanked out."""
    # Bytes, not text: on Windows a text pipe turns LF into CRLF, which breaks the scripts sent to Linux containers
    p = subprocess.run(cmd, input=stdin.encode() if stdin else None, capture_output=True, timeout=300, creationflags=NO_WINDOW)
    out = (p.stdout + p.stderr).decode(errors="replace")
    for s in secret:
        out = out.replace(s, "***")
    if p.returncode != 0:
        last = [line for line in out.splitlines() if line.strip()][-1:] or ["no output"]
        raise RuntimeError(f"{' '.join(cmd[:4])} failed: {last[0][:300]}")
    return out


def postgres(container, env):
    role, password = env["PG_APP_USER"], env["PG_APP_PASSWORD"]
    dbs = databases(role[:-len("_app")])
    # Variables travel on stdin, never in argv; psql quotes them (:'literal', :"identifier")
    head = "".join(f"\\set {k} '{v}'\n" for k, v in {"role": role, "password": password, "db1": dbs[0], "db2": dbs[1]}.items())
    sql = head + r"""
SELECT format('CREATE ROLE %I LOGIN', :'role') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'role') \gexec
ALTER ROLE :"role" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'password';
SELECT format('CREATE DATABASE %I OWNER %I', d, :'role') FROM unnest(ARRAY[:'db1', :'db2']) AS d
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = d) \gexec
-- The owner's databases existed before its role; they and their schema public move to it
SELECT format('ALTER DATABASE %I OWNER TO %I', d, :'role') FROM unnest(ARRAY[:'db1', :'db2']) AS d \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', d) FROM unnest(ARRAY[:'db1', :'db2']) AS d \gexec
SELECT format('GRANT ALL ON DATABASE %I TO %I', d, :'role') FROM unnest(ARRAY[:'db1', :'db2']) AS d \gexec
-- The maintenance database is open to every role by default; no client needs it
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
"""
    run(["docker", "exec", "-i", container, "sh", "-c", 'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'],
        stdin=sql, secret=[password])
    # Tables, partitions and sequences someone else created (the owner's, made by the admin login before D-037) move to
    # the role one by one. Never REASSIGN OWNED: it would move databases and tablespaces too. Sequences that belong to a
    # table column move with their table.
    transfer = f"\\set role '{role}'\n" + r"""
SELECT format('ALTER %s %s OWNER TO %I',
              CASE c.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
              c.oid::regclass, :'role')
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
   AND c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = :'role')
   AND NOT (c.relkind = 'S' AND EXISTS (SELECT FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i'))) \gexec
"""
    for db in dbs:
        run(["docker", "exec", "-i", container, "sh", "-c", f'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "{db}"'],
            stdin=transfer)


def postgres_role_exists(container, role):
    out = run(["docker", "exec", "-i", container, "sh", "-c", 'exec psql -X -At -U "$POSTGRES_USER" -d postgres'],
              stdin=f"\\set role '{role}'\nSELECT count(*) FROM pg_roles WHERE rolname = :'role';\n")
    return out.strip().endswith("1")


def milvus_call(url, token, path, body, secret=()):
    """Milvus REST v2; success is code 0 in the body, whatever the HTTP status."""
    request = urllib.request.Request(f"{url}/v2/vectordb/{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:  # refusals come as 4xx with the reason in the body
        try:
            out = json.load(e)
        except ValueError:
            raise RuntimeError(f"Milvus {path}: HTTP {e.code}") from None
    except (urllib.error.URLError, ValueError) as e:
        raise RuntimeError(f"Milvus {path}: {e}") from None
    if out.get("code") != 0:
        message = str(out.get("message", ""))
        for s in secret:
            message = message.replace(s, "***")
        raise RuntimeError(f"Milvus {path}: code {out.get('code')}: {message[:200]}")
    return out.get("data")


def milvus(url, root_token, env):
    user, password = env["MILVUS_APP_USER"], env["MILVUS_APP_PASSWORD"]
    db, role = milvus_database(user[:-len("_app")]), f"{user[:-len('_app')]}_role"
    call = lambda path, body: milvus_call(url, root_token, path, body, secret=[password, root_token])  # noqa: E731
    if db not in call("databases/list", {}):
        call("databases/create", {"dbName": db})
    if user not in call("users/list", {}):
        call("users/create", {"userName": user, "password": password})
    if role not in call("roles/list", {}):
        call("roles/create", {"roleName": role})
    for group in MILVUS_GROUPS:
        call("roles/grant_privilege_v2", {"roleName": role, "privilege": group, "collectionName": "*", "dbName": db})
    call("users/grant_role", {"userName": user, "roleName": role})
    # The saved password must work: a user created by an earlier run with another password would fail here
    milvus_call(url, f"{user}:{password}", "collections/list", {"dbName": db}, secret=[password])


def milvus_user_exists(url, root_token, user):
    return user in milvus_call(url, root_token, "users/list", {}, secret=[root_token])


def kafka(container, env):
    client = env["KAFKA_APP_USER"][:-len("_app")]
    admin = ["docker", "exec", container]
    boot = ["--bootstrap-server", "localhost:29092"]  # the broker's loopback listener (STANDALONE-SERVICES/auth/kafka.env)
    for user, key in ((env["KAFKA_APP_USER"], "KAFKA_APP_PASSWORD"), (env["KAFKA_DISPLAY_USER"], "KAFKA_DISPLAY_PASSWORD")):
        run(admin + ["kafka-configs", *boot, "--alter", "--entity-type", "users", "--entity-name", user,
                     "--add-config", f"SCRAM-SHA-512=[password={env[key]}]"], secret=[env[key]])
    acls = [(env["KAFKA_APP_USER"], op, "--topic") for op in ("Write", "Describe")]
    acls += [(env["KAFKA_DISPLAY_USER"], op, "--topic") for op in ("Read", "Describe")]
    acls += [(env["KAFKA_DISPLAY_USER"], "Read", "--group")]
    for user, op, kind in acls:
        # The trailing dot ends the prefix: IDs hold none, so acme. never covers acmeb.
        run(admin + ["kafka-acls", *boot, "--add", "--allow-principal", f"User:{user}", "--operation", op, kind,
                     f"{client}.", "--resource-pattern-type", "prefixed"])


def topics(camera_config, client):
    """{topic: partitions} from the site's camera configuration: one topic per point, one partition per camera, where
    cctv-camera-N writes to partition N-1 (src/util/generic_utilities.py), so gaps in the numbering still fit."""
    config = json.loads(camera_config.read_text(encoding="utf-8"))
    wanted = {}
    for location, data in config.items():
        for point, cameras in (data.get("cctv-cameras") or {}).items():
            if cameras:
                wanted[f"{client}.{location}_{point}"] = max(len(cameras), *(int(c.rsplit("-", 1)[-1]) for c in cameras))
    return wanted


def kafka_topics(container, wanted):
    """Create missing topics and add partitions for new cameras; the app may only write (D-037). Never shrinks."""
    admin = ["docker", "exec", container, "kafka-topics", "--bootstrap-server", "localhost:29092"]
    for topic, partitions in wanted.items():
        # Same settings the app used: displays need only the latest messages (src/parameters.py retention)
        run(admin + ["--create", "--if-not-exists", "--topic", topic, "--partitions", str(partitions),
                     "--config", "retention.ms=5000", "--config", "segment.ms=5000"])
        have = re.search(r"PartitionCount:\s*(\d+)", run(admin + ["--describe", "--topic", topic]))
        if have and int(have[1]) < partitions:
            run(admin + ["--alter", "--topic", topic, "--partitions", str(partitions)])


# The collections the app expects (src/parameters.py, METRIC_TYPE COSINE); the app adds the indexes at start
PRIMARY, STAGING = "FACE_DATA_COLLECTION_FOR_COSINE", "FACE_DATA_STAGING_COLLECTION_FOR_COSINE"
SCHEMA = {"autoId": False, "enableDynamicField": False, "fields": [
    {"fieldName": "name_id", "dataType": "VarChar", "isPrimary": True, "elementTypeParams": {"max_length": 60}},
    {"fieldName": "embeddings", "dataType": "FloatVector", "elementTypeParams": {"dim": 512}}]}


def milvus_collections(url, root_token, db):
    """A new client starts with an empty numbered version behind the alias (D-030), so the app never makes a plain
    collection under the alias's name. An existing alias or collection is left as it is."""
    call = lambda path, body: milvus_call(url, root_token, path, body, secret=[root_token])  # noqa: E731
    existing = call("collections/list", {"dbName": db})
    aliases = call("aliases/list", {"dbName": db}) or []
    if PRIMARY not in aliases and PRIMARY not in existing:
        if f"{PRIMARY}_v1" not in existing:
            call("collections/create", {"dbName": db, "collectionName": f"{PRIMARY}_v1", "schema": SCHEMA})
        call("aliases/create", {"dbName": db, "collectionName": f"{PRIMARY}_v1", "aliasName": PRIMARY})
    if STAGING not in existing:
        call("collections/create", {"dbName": db, "collectionName": STAGING, "schema": SCHEMA})


def kafka_user_exists(container, user):
    out = run(["docker", "exec", container, "kafka-configs", "--bootstrap-server", "localhost:29092", "--describe",
               "--entity-type", "users", "--entity-name", user])
    return "SCRAM-SHA-512" in out


def store_script(env):
    bucket, key, secret = f"{env['STORE_APP_ACCESS_KEY'][:-len('-app')]}-enrolment", env["STORE_APP_ACCESS_KEY"], env["STORE_APP_SECRET_KEY"]
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketLocation"],
         "Resource": [f"arn:aws:s3:::{bucket}"]},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:DeleteObject",
                                       "s3:DeleteObjectVersion"], "Resource": [f"arn:aws:s3:::{bucket}/*"]}]}
    return bucket, key, secret, f"""set -e
mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing local/{bucket} >/dev/null
cat > /tmp/{key}.json <<'POLICY'
{json.dumps(policy)}
POLICY
mc admin policy create local {key} /tmp/{key}.json >/dev/null
rm -f /tmp/{key}.json
mc admin user add local {key} {secret} >/dev/null
mc admin policy attach local {key} --user {key} >/dev/null 2>&1 || mc admin policy entities local --user {key} | grep -q {key}
"""


def store(container, env):
    _, _, secret, script = store_script(env)
    run(["docker", "exec", "-i", container, "sh", "-s"], stdin=script, secret=[secret])


def store_user_exists(container, key):
    script = f'mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null\nmc admin user info local {key} >/dev/null 2>&1 && echo yes || echo no\n'
    return run(["docker", "exec", "-i", container, "sh", "-s"], stdin=script).strip().endswith("yes")


def root_token(admin_env):
    password = read_env(admin_env).get("MILVUS_ROOT_PASSWORD")
    if not password:
        raise Stop(f"No MILVUS_ROOT_PASSWORD in {admin_env}: run python provision.py --init-milvus-root first")
    return f"root:{password}"


def provision(client, sites, admin_env, pg, kafka_container, store_container, milvus_url):
    if not CLIENT_ID.fullmatch(client):
        raise Stop(f"{client!r} is not a client ID: 3 to 30 lowercase letters or digits, starting with a letter")
    token = root_token(admin_env)
    site_env = sites / client / ".env"
    cameras = sites / client / "src/Camera-Configuration/camera_configuration.json"
    if not cameras.is_file():
        raise Stop(f"{cameras} is missing: its points and cameras decide the client's Kafka topics and partitions")
    wanted_topics = topics(cameras, client)
    env = settings(client)
    # An account that exists while its password is not saved belongs to an earlier run whose password is lost;
    # resetting it would lock out the stack that uses the old one. Checked before anything is written.
    exists = {
        "PG_APP_PASSWORD": lambda: postgres_role_exists(pg, env["PG_APP_USER"]),
        "MILVUS_APP_PASSWORD": lambda: milvus_user_exists(milvus_url, token, env["MILVUS_APP_USER"]),
        "KAFKA_APP_PASSWORD": lambda: kafka_user_exists(kafka_container, env["KAFKA_APP_USER"]),
        "KAFKA_DISPLAY_PASSWORD": lambda: kafka_user_exists(kafka_container, env["KAFKA_DISPLAY_USER"]),
        "STORE_APP_SECRET_KEY": lambda: store_user_exists(store_container, env["STORE_APP_ACCESS_KEY"]),
    }
    saved = read_env(site_env)
    lost = sorted(key for key in exists if key not in saved and exists[key]())
    if lost:
        raise Stop(f"{client}: {', '.join(lost)} not in {site_env}, but the account exists. Put the stack's current "
                   f"value back into {site_env}, or remove the account on purpose, then rerun")
    env = save_missing(site_env, env)  # new passwords are saved before any service is touched
    postgres(pg, env)
    milvus(milvus_url, token, env)
    milvus_collections(milvus_url, token, milvus_database(client))
    kafka(kafka_container, env)
    kafka_topics(kafka_container, wanted_topics)
    store(store_container, env)
    print(f"{client}: provisioned (PostgreSQL, Milvus, Kafka with {len(wanted_topics)} topics, dataset store); "
          f"credentials in {site_env}")


def init_milvus_root(admin_env, milvus_url):
    """Replace root's default password. The new one is saved first, so a crash midway is finished by a rerun."""
    env = save_missing(admin_env, {"MILVUS_ROOT_PASSWORD": None})
    new = env["MILVUS_ROOT_PASSWORD"]
    try:
        milvus_call(milvus_url, f"root:{new}", "users/list", {}, secret=[new])
        print("Milvus root password already replaced")
        return
    except RuntimeError:
        pass
    milvus_call(milvus_url, "root:Milvus", "users/update_password",
                {"userName": "root", "password": "Milvus", "newPassword": new}, secret=[new])
    milvus_call(milvus_url, f"root:{new}", "users/list", {}, secret=[new])
    print(f"Milvus root password replaced; it is in {admin_env}")


def init_kafbat(admin_env, container):
    """A read-only Kafka login for the loopback-only Kafbat UI, which browses every client's topics (D-037). Rerunning
    sets the saved password again; only the UI uses it."""
    password = save_missing(admin_env, {"KAFBAT_PASSWORD": None})["KAFBAT_PASSWORD"]
    admin = ["docker", "exec", container]
    boot = ["--bootstrap-server", "localhost:29092"]
    run(admin + ["kafka-configs", *boot, "--alter", "--entity-type", "users", "--entity-name", "kafbat",
                 "--add-config", f"SCRAM-SHA-512=[password={password}]"], secret=[password])
    grants = [(op, ["--topic", "*"]) for op in ("Read", "Describe", "DescribeConfigs")]
    grants += [(op, ["--group", "*"]) for op in ("Read", "Describe")]
    grants += [(op, ["--cluster"]) for op in ("Describe", "DescribeConfigs")]
    for op, resource in grants:
        run(admin + ["kafka-acls", *boot, "--add", "--allow-principal", "User:kafbat", "--operation", op, *resource])
    print(f"Kafbat login ready; its password is in {admin_env}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("client", nargs="?")
    parser.add_argument("--init-milvus-root", action="store_true")
    parser.add_argument("--init-kafbat", action="store_true")
    parser.add_argument("--sites", type=Path, default=ROOT / "sites")
    parser.add_argument("--admin-env", type=Path, default=ROOT / "admin.env")
    parser.add_argument("--postgres", default="cctv-postgresql")
    parser.add_argument("--kafka", default="broker")
    parser.add_argument("--store", default="dataset-store")
    parser.add_argument("--milvus", default="http://localhost:19530")
    args = parser.parse_args(argv)
    try:
        if args.init_milvus_root:
            init_milvus_root(args.admin_env, args.milvus)
        elif args.init_kafbat:
            init_kafbat(args.admin_env, args.kafka)
        elif args.client:
            provision(args.client, args.sites, args.admin_env, args.postgres, args.kafka, args.store, args.milvus)
        else:
            parser.error("give a client ID or --init-milvus-root")
    except (Stop, RuntimeError) as e:
        print(f"Provisioning stopped: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
