"""Snapshot, restore and remove one client on this host's shared services (D-042), leaving every other client alone.

  python recovery.py snapshot CLIENT             writes sites/CLIENT/snapshots/<time>: both databases, the bucket, the site's data
  python recovery.py restore CLIENT FOLDER       puts a snapshot back; the client's stack must be down. Deletions the live
                                                 database records (8e) are re-run, so nobody deleted comes back
  python recovery.py remove CLIENT --confirm CLIENT   deletes the client everywhere, its site folder too; the owner is refused,
                                                      and the ID cannot be used again on this Kafka
Options as in provision.py: --sites DIR, --admin-env FILE, --postgres/--kafka/--store/--proxy CONTAINER, --milvus URL.

Milvus is never copied: rows share a person's ID as primary key, so vectors cannot be read back out (D-030). The vectors.parquet
files in the snapshot rebuild it, through the release's own `face_vectors.py publish`. A snapshot holds no passwords: they stay
in the site's .env, and it sits beside the data it protects, so it is not an off-host backup.
Stdlib only, like provision.py and watch.py.
"""
import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import provision
from provision import CLIENT_ID, NO_WINDOW, OWNER, ROOT, Stop, read_env, run

DATA = ["FACIAL-RECOGNITION-DATASET", "DYNAMIC-FACIAL-RECOGNITION-DATASET", "DISPLAY-FACE-DATASET", "src/Camera-Configuration"]
VECTORS = "FACIAL-RECOGNITION-DATASET"
ADMIN_MC = 'mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null\n'
LONG = 1800  # seconds; a client's databases and photos can take a while


def bucket(client):
    return f"{client}-enrolment"


def project(client):
    return "cctv" if client == OWNER else f"cctv-{client}"


def containers(client):
    """Every container of the client's stack, running or not."""
    return run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project(client)}"]).split()


def to_file(cmd, path):
    with open(path, "wb") as out:
        p = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, timeout=LONG, creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])} failed: {p.stderr.decode(errors='replace').strip()[-300:]}")


def from_file(cmd, path):
    with open(path, "rb") as source:
        p = subprocess.run(cmd, stdin=source, capture_output=True, timeout=LONG, creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])} failed: {p.stderr.decode(errors='replace').strip()[-300:]}")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def admin_sql(pg, sql):
    run(["docker", "exec", "-i", pg, "sh", "-c", 'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'], stdin=sql)


def snapshot(client, sites, pg, store):
    site = sites / client
    folder = site / "snapshots" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True)
    for db in provision.databases(client):
        to_file(["docker", "exec", pg, "sh", "-c", 'exec pg_dump -U "$POSTGRES_USER" -Fc "$0"', db], folder / f"{db}.dump")
    work = f"/tmp/snapshot-{client}"  # this image has no tar, so the files come out with docker cp
    run(["docker", "exec", "-i", store, "sh", "-s"], stdin=ADMIN_MC + f"set -e\nrm -rf {work}\nmkdir {work}\nmc mirror --quiet local/{bucket(client)} {work} >/dev/null\n")
    with tempfile.TemporaryDirectory() as tmp:
        run(["docker", "cp", f"{store}:{work}", f"{tmp}/bucket"])
        with tarfile.open(folder / "bucket.tar", "w") as tar:
            tar.add(f"{tmp}/bucket", arcname=".")
    run(["docker", "exec", store, "rm", "-rf", work])
    with tarfile.open(folder / "site.tar.gz", "w:gz") as tar:
        for name in DATA:
            if (site / name).exists():
                tar.add(site / name, arcname=name)
    state = json.loads((site / "state.json").read_text(encoding="utf-8")) if (site / "state.json").is_file() else {}
    files = {path.name: digest(path) for path in folder.iterdir()}
    (folder / "snapshot.json").write_text(json.dumps({"client": client, "release": state.get("current"), "files": files}, indent=2) + "\n", encoding="utf-8")
    print(f"{client}: snapshot in {folder}")
    return folder


def check_snapshot(client, folder):
    manifest = folder / "snapshot.json"
    if not manifest.is_file():
        raise Stop(f"{folder} is not a snapshot: no snapshot.json")
    info = json.loads(manifest.read_text(encoding="utf-8"))
    if info.get("client") != client:
        raise Stop(f"{folder} belongs to {info.get('client')!r}, not {client!r}")
    for name, want in info["files"].items():
        if not (folder / name).is_file() or digest(folder / name) != want:
            raise Stop(f"{folder / name} is missing or changed since the snapshot")


def publish(client, sites):
    """Rebuild Milvus from the restored vectors.parquet files, with the client's own login, in the release's image."""
    site = sites / client
    if not any((site / VECTORS).glob("*/vectors.parquet")):
        print(f"{client}: no vectors.parquet in the snapshot, so Milvus keeps what it has")
        return
    tag = json.loads((site / "state.json").read_text(encoding="utf-8"))["current"]
    run(["docker", "compose", "-p", project(client), "--project-directory", str(site), "-f", str(ROOT / "releases" / tag / "docker-compose-main.yml"),
         "run", "--rm", "--no-deps", "-T", "-v", f"{(site / VECTORS).as_posix()}:/Multi-Person-Face-Recognition/{VECTORS}:ro",
         "mfr-cctv-producer-consumer", "python3", "src/util/face_vectors.py", "publish"])


def db_sql(pg, db, sql):
    return run(["docker", "exec", "-i", pg, "sh", "-c", 'exec psql -X -q -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$0"', db], stdin=sql).strip()


def recorded_deletions(pg, db):
    """The deletions (8e) the live database records, the latest per person, as JSON. A restore re-runs them, so a
    snapshot taken before someone was deleted cannot bring their face data back."""
    if db_sql(pg, "postgres", f"SELECT count(*) FROM pg_database WHERE datname = '{db}'") == "0" or \
            db_sql(pg, db, "SELECT to_regclass('deletions') IS NULL") == "t":
        return []
    return json.loads(db_sql(pg, db, "SELECT coalesce(json_agg(d), '[]') FROM (SELECT DISTINCT ON (person_id) id, person_id, reason, "
                                     "requested_by, requested_at FROM deletions ORDER BY person_id, requested_at DESC) d"))


def reopen_deletions(pg, db, role, site, deletions):
    """Re-runs the recorded deletions on the restored data: the person's folders go now, before Milvus is rebuilt from
    them, and the open requests let the enrolment worker delete the rest when the stack starts."""
    if not deletions:
        return
    for request in deletions:
        for name in DATA[:3]:
            base = (site / name).resolve()
            target = (base / request["person_id"]).resolve()
            if target.parent == base:  # only a person's own folder, never anything an odd ID could point at
                shutil.rmtree(target, ignore_errors=True)
    rows = json.dumps(deletions)
    if "$d8e$" in rows:
        raise Stop("a recorded deletion holds the text $d8e$, which this restore uses to quote them")
    # The table as src/api/enrolment.py creates it, for a snapshot from before 8e; owned by the app, which writes to it
    db_sql(pg, db, f"""CREATE TABLE IF NOT EXISTS deletions (id UUID PRIMARY KEY, person_id TEXT NOT NULL, reason TEXT NOT NULL,
    requested_by TEXT NOT NULL, requested_at TIMESTAMPTZ NOT NULL DEFAULT now(), done_at TIMESTAMPTZ, frames_cleared_at TIMESTAMPTZ);
CREATE UNIQUE INDEX IF NOT EXISTS deletions_one_open ON deletions (person_id) WHERE done_at IS NULL;
ALTER TABLE deletions OWNER TO "{role}";
DELETE FROM deletions d USING json_populate_recordset(NULL::deletions, $d8e${rows}$d8e$) r WHERE d.person_id = r.person_id AND d.done_at IS NULL AND d.id <> r.id;
INSERT INTO deletions (id, person_id, reason, requested_by, requested_at)
SELECT id, person_id, reason, requested_by, requested_at FROM json_populate_recordset(NULL::deletions, $d8e${rows}$d8e$)
ON CONFLICT (id) DO UPDATE SET done_at = NULL, frames_cleared_at = NULL;""")
    print(f"{site.name}: {len(deletions)} recorded deletion(s) re-opened for the enrolment worker")


def restore(client, folder, sites, admin_env, pg, kafka, store, milvus):
    check_snapshot(client, folder)
    if containers(client):
        raise Stop(f"{client}'s stack still has containers: stop it with docker compose -p {project(client)} down first")
    site = sites / client
    dbs = provision.databases(client)
    deletions = recorded_deletions(pg, dbs[0])  # read before the live database is dropped
    for name in DATA:
        shutil.rmtree(site / name, ignore_errors=True)
    with tarfile.open(folder / "site.tar.gz") as tar:
        tar.extractall(site, filter="data")
    admin_sql(pg, "".join(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE);\n' for db in dbs))
    provision.provision(client, sites, admin_env, pg, kafka, store, milvus)  # the empty databases, and anything else lost, with the saved passwords
    role = read_env(site / ".env")["PG_APP_USER"]
    for db in dbs:
        from_file(["docker", "exec", "-i", pg, "sh", "-c", 'exec pg_restore -U "$POSTGRES_USER" --no-owner --role="$0" --exit-on-error -d "$1"', role, db], folder / f"{db}.dump")
    reopen_deletions(pg, dbs[0], role, site, deletions)
    work = f"/tmp/restore-{client}"
    run(["docker", "exec", store, "rm", "-rf", work])
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(folder / "bucket.tar") as tar:
            tar.extractall(tmp, filter="data")
        run(["docker", "cp", tmp, f"{store}:{work}"])
    run(["docker", "exec", "-i", store, "sh", "-s"], stdin=ADMIN_MC + f"set -e\nmc mirror --quiet --remove --overwrite {work} local/{bucket(client)} >/dev/null\nrm -rf {work}\n")
    publish(client, sites)
    print(f"{client}: restored from {folder}")


def remove_kafka(container, env, client):
    admin = ["docker", "exec", container]
    boot = ["--bootstrap-server", "localhost:29092"]
    prefix = f"{client}."  # the trailing dot ends the prefix, as in provision.kafka: acme. never covers acmeb.
    for topic in run(admin + ["kafka-topics", *boot, "--list"]).split():
        if topic.startswith(prefix):
            run(admin + ["kafka-topics", *boot, "--delete", "--topic", topic])
    for group in run(admin + ["kafka-consumer-groups", *boot, "--list"]).split():
        if group.startswith(prefix):
            run(admin + ["kafka-consumer-groups", *boot, "--delete", "--group", group])
    for kind in ("--topic", "--group"):
        run(admin + ["kafka-acls", *boot, "--remove", "--force", kind, prefix, "--resource-pattern-type", "prefixed"])
    # Never --delete-config: on cp-kafka 8.4.0, deleting one SCRAM login loses every client's login at the next broker
    # restart (D-042). A password nobody holds, with no ACLs, ends the login just as well; the name stays, so the ID is spent.
    for user in (env["KAFKA_APP_USER"], env["KAFKA_DISPLAY_USER"]):
        password = secrets.token_hex(32)
        run(admin + ["kafka-configs", *boot, "--alter", "--entity-type", "users", "--entity-name", user, "--add-config", f"SCRAM-SHA-512=[password={password}]"], secret=[password])


def remove_milvus(url, token, env, client):
    call = lambda path, body: provision.milvus_call(url, token, path, body, secret=[token])  # noqa: E731
    db, user, role = provision.milvus_database(client), env["MILVUS_APP_USER"], f"{client}_role"
    if db in call("databases/list", {}):
        for alias in call("aliases/list", {"dbName": db}) or []:
            call("aliases/drop", {"dbName": db, "aliasName": alias})
        for collection in call("collections/list", {"dbName": db}) or []:
            call("collections/drop", {"dbName": db, "collectionName": collection})
    if user in call("users/list", {}) and role in call("roles/list", {}):
        call("users/revoke_role", {"userName": user, "roleName": role})
    if role in call("roles/list", {}):
        for group in provision.MILVUS_GROUPS:
            call("roles/revoke_privilege_v2", {"roleName": role, "privilege": group, "collectionName": "*", "dbName": db})
        call("roles/drop", {"roleName": role})
    if user in call("users/list", {}):
        call("users/drop", {"userName": user})
    if db in call("databases/list", {}):
        call("databases/drop", {"dbName": db})


def remove_store(container, env, client):
    key = env["STORE_APP_ACCESS_KEY"]
    script = ADMIN_MC + f"mc rb --force local/{bucket(client)} >/dev/null 2>&1\nmc admin user rm local {key} >/dev/null 2>&1\nmc admin policy remove local {key} >/dev/null 2>&1\n" \
        f'mc ls local/{bucket(client)} >/dev/null 2>&1 && exit 1\nexit 0\n'
    run(["docker", "exec", "-i", container, "sh", "-s"], stdin=script)


def remove_route(client, sites, proxy):
    (sites.parent / "proxy" / f"{client}.caddy").unlink(missing_ok=True)
    if run(["docker", "ps", "-q", "--filter", f"name=^{proxy}$"]).strip():
        run(["docker", "exec", proxy, "caddy", "reload", "--config", "/etc/caddy/Caddyfile"])


def remove(client, confirm, sites, admin_env, pg, kafka, store, milvus, proxy):
    if client == OWNER:
        raise Stop("the owner's site is never removed by this command")
    if confirm != client:
        raise Stop(f"nothing removed: --confirm must repeat the client ID {client!r}")
    if containers(client):
        raise Stop(f"{client}'s stack still has containers: stop it with docker compose -p {project(client)} down first")
    env = read_env(sites / client / ".env")
    if not env:
        raise Stop(f"{sites / client / '.env'} is missing, so {client} is not a client of this host")
    remove_kafka(kafka, env, client)
    remove_milvus(milvus, provision.root_token(admin_env), env, client)
    remove_store(store, env, client)
    admin_sql(pg, "".join(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE);\n' for db in provision.databases(client)) + f'DROP ROLE IF EXISTS "{env["PG_APP_USER"]}";\n')
    remove_route(client, sites, proxy)
    shutil.rmtree(sites / client)  # last: its .env is what lets an interrupted remove run again
    print(f"{client}: removed from PostgreSQL, Milvus, Kafka, the dataset store, the proxy and this host")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["snapshot", "restore", "remove"])
    parser.add_argument("client")
    parser.add_argument("folder", nargs="?", type=Path, help="the snapshot to restore")
    parser.add_argument("--confirm", help="the client ID again, for remove")
    parser.add_argument("--sites", type=Path, default=ROOT / "sites")
    parser.add_argument("--admin-env", type=Path, default=ROOT / "admin.env")
    parser.add_argument("--postgres", default="cctv-postgresql")
    parser.add_argument("--kafka", default="broker")
    parser.add_argument("--store", default="dataset-store")
    parser.add_argument("--milvus", default="http://localhost:19530")
    parser.add_argument("--proxy", default="cctv-proxy")
    args = parser.parse_args(argv)
    services = (args.admin_env, args.postgres, args.kafka, args.store, args.milvus)
    try:
        if not CLIENT_ID.fullmatch(args.client):
            raise Stop(f"{args.client!r} is not a client ID")
        if args.command == "snapshot":
            snapshot(args.client, args.sites, args.postgres, args.store)
        elif args.command == "restore":
            if not args.folder:
                parser.error("restore needs the snapshot folder")
            restore(args.client, args.folder, args.sites, *services)
        else:
            remove(args.client, args.confirm, args.sites, *services, args.proxy)
    except (Stop, RuntimeError) as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
